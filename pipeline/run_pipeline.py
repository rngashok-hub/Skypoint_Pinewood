from pathlib import Path
from datetime import datetime
import ast
import re

import pandas as pd
import duckdb


# ============================================================
# 1. PROJECT PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
BRONZE_DIR = BASE_DIR / "bronze"
SILVER_DIR = BASE_DIR / "silver"
GOLD_DIR = BASE_DIR / "gold"
LOG_DIR = BASE_DIR / "logs"
QUARANTINE_DIR = BASE_DIR / "quarantine"

DB_PATH = GOLD_DIR / "pinewood.duckdb"

for folder in [
    BRONZE_DIR,
    SILVER_DIR,
    GOLD_DIR,
    LOG_DIR,
    QUARANTINE_DIR
]:
    folder.mkdir(parents=True, exist_ok=True)


# ============================================================
# 2. RUN LOGGING
# ============================================================

RUN_TIMESTAMP = datetime.now().isoformat()

run_log = []
quarantine_log = []


def add_log(source_file, layer, status, rows, message):
    run_log.append({
        "run_timestamp": RUN_TIMESTAMP,
        "source_file": source_file,
        "layer": layer,
        "status": status,
        "rows": rows,
        "message": message
    })


def add_quarantine(source_file, reason, rows):
    quarantine_log.append({
        "run_timestamp": RUN_TIMESTAMP,
        "source_file": source_file,
        "reason": reason,
        "rows": rows
    })


# ============================================================
# 3. HELPER FUNCTIONS
# ============================================================

def get_source_name(filename):
    """
    Example:
    adp_shifts_2025_01.csv
    becomes:
    adp_shifts
    """

    name = Path(filename).stem

    return re.sub(
        r"_\d{4}_\d{2}$",
        "",
        name
    )


def normalize_care_level(value):

    if pd.isna(value):
        return None

    value = str(value).strip().lower()

    mapping = {

        "il": "Independent Living",
        "independent": "Independent Living",
        "independent living": "Independent Living",

        "al": "Assisted Living",
        "assisted": "Assisted Living",
        "assisted living": "Assisted Living",

        "mc": "Memory Care",
        "memory": "Memory Care",
        "memory care": "Memory Care"
    }

    return mapping.get(
        value,
        str(value).strip()
    )


def extract_hourly_rate(rate_value, role):

    if pd.isna(rate_value):
        return None

    # Already numeric
    try:

        numeric_value = float(rate_value)

        if numeric_value > 0:
            return numeric_value

    except (ValueError, TypeError):

        pass

    # Dictionary stored as text
    try:

        rate_dictionary = ast.literal_eval(
            str(rate_value)
        )

        if isinstance(rate_dictionary, dict):

            value = rate_dictionary.get(role)

            if value is not None:
                return float(value)

    except Exception:

        pass

    return None


DATE_COLUMNS = {
    "dob",
    "admit_date",
    "discharge_date",
    "change_date",
    "incident_date",
    "move_in_date",
    "move_out_date",
    "shift_date",
    "review_date",
    "responded_at",
    "created_date",
    "tour_date",
    "deposit_date",
    "snapshot_date"
}


NUMERIC_COLUMNS = {
    "acuity_score",
    "severity",
    "hours_worked",
    "monthly_rate",
    "monthly_rent",
    "rating"
}


def convert_dates(df):

    for column in DATE_COLUMNS:

        if column in df.columns:

            df[column] = pd.to_datetime(
                df[column],
                errors="coerce"
            )

    return df


def convert_numeric(df):

    for column in NUMERIC_COLUMNS:

        if column in df.columns:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

    return df


# ============================================================
# 4. BRONZE LAYER
# ============================================================

def create_bronze(con):

    print("\n" + "=" * 60)
    print("BRONZE LAYER")
    print("=" * 60)

    csv_files = sorted(
        DATA_DIR.glob("*.csv")
    )

    # Group files by source table
    source_groups = {}

    for file in csv_files:

        source_name = get_source_name(
            file.name
        )

        source_groups.setdefault(
            source_name,
            []
        ).append(file)

    for source_name, files in sorted(
        source_groups.items()
    ):

        print(
            f"\n[BRONZE] Processing {source_name}"
        )

        all_dataframes = []

        for file in sorted(files):

            try:

                # dtype=str keeps Bronze as close
                # to the raw source as possible
                df = pd.read_csv(
                    file,
                    dtype=str
                )

                # Ingestion metadata
                df["source_file"] = file.name
                df["ingestion_timestamp"] = RUN_TIMESTAMP

                all_dataframes.append(df)

                add_log(
                    file.name,
                    "Bronze",
                    "PROCESSED",
                    len(df),
                    "Raw file loaded"
                )

                print(
                    f"  {file.name}: {len(df):,} rows"
                )

            except Exception as e:

                add_log(
                    file.name,
                    "Bronze",
                    "REJECTED",
                    0,
                    str(e)
                )

                print(
                    f"  ERROR: {file.name}: {e}"
                )

        if not all_dataframes:
            continue

        # Handles schema drift such as April
        # pcc_residents having mobility_status
        combined_df = pd.concat(
            all_dataframes,
            ignore_index=True,
            sort=False
        )

        con.register(
            "bronze_input",
            combined_df
        )

        table_name = (
            f"bronze_{source_name}"
        )

        con.execute(
            f"""
            CREATE OR REPLACE TABLE {table_name}
            AS
            SELECT *
            FROM bronze_input
            """
        )

        # Also save Bronze as parquet
        parquet_path = (
            BRONZE_DIR /
            f"{source_name}.parquet"
        )

        combined_df.to_parquet(
            parquet_path,
            index=False
        )

        print(
            f"  TOTAL: {len(combined_df):,} rows"
        )


# ============================================================
# 5. SILVER LAYER
# ============================================================

def create_silver(con):

    print("\n" + "=" * 60)
    print("SILVER LAYER")
    print("=" * 60)

    tables = con.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_name LIKE 'bronze_%'
        AND table_name NOT LIKE '%input%'
        ORDER BY table_name
        """
    ).fetchdf()

    for table_name in tables["table_name"]:

        source_name = table_name.replace(
            "bronze_",
            ""
        )

        try:

            df = con.execute(
                f"SELECT * FROM {table_name}"
            ).df()

            original_rows = len(df)

            # Remove exact duplicate records
            df = df.drop_duplicates()

            # ------------------------------------------------
            # CARE LEVEL STANDARDIZATION
            # ------------------------------------------------

            for column in [
                "care_level",
                "previous_level",
                "new_level"
            ]:

                if column in df.columns:

                    df[column] = df[column].apply(
                        normalize_care_level
                    )

            # ------------------------------------------------
            # ADP HOURLY RATE CLEANING
            # ------------------------------------------------

            if (
                source_name == "adp_shifts"
                and "hourly_rate" in df.columns
                and "role" in df.columns
            ):

                df["hourly_rate"] = df.apply(
                    lambda row:
                    extract_hourly_rate(
                        row["hourly_rate"],
                        row["role"]
                    ),
                    axis=1
                )

            # ------------------------------------------------
            # DATE STANDARDIZATION
            # ------------------------------------------------

            df = convert_dates(df)

            # ------------------------------------------------
            # NUMERIC STANDARDIZATION
            # ------------------------------------------------

            df = convert_numeric(df)

            # ------------------------------------------------
            # PCC ACUITY VALIDATION
            # ------------------------------------------------

            if (
                source_name == "pcc_residents"
                and "acuity_score" in df.columns
            ):

                invalid_acuity = (
                    df["acuity_score"].notna()
                    &
                    ~df["acuity_score"].between(
                        1,
                        10
                    )
                )

                invalid_count = int(
                    invalid_acuity.sum()
                )

                if invalid_count > 0:

                    bad_rows = df.loc[
                        invalid_acuity
                    ].copy()

                    bad_rows.to_csv(
                        QUARANTINE_DIR /
                        "pcc_residents_invalid_acuity.csv",
                        index=False
                    )

                    add_quarantine(
                        source_name,
                        "Acuity score outside documented 1-10 range",
                        invalid_count
                    )

                    # Keep record but remove invalid value
                    df.loc[
                        invalid_acuity,
                        "acuity_score"
                    ] = None

            # ------------------------------------------------
            # COMMUNITY ID VALIDATION
            # ------------------------------------------------

            if "community_id" in df.columns:

                valid_pattern = (
                    r"^C(00[1-9]|0(1[0-4]))$"
                )

                invalid_communities = (
                    df["community_id"].notna()
                    &
                    ~df["community_id"].astype(str).str.match(
                        valid_pattern,
                        na=False
                    )
                )

                invalid_count = int(
                    invalid_communities.sum()
                )

                if invalid_count > 0:

                    bad_rows = df.loc[
                        invalid_communities
                    ].copy()

                    bad_rows.to_csv(
                        QUARANTINE_DIR /
                        f"{source_name}_invalid_community.csv",
                        index=False
                    )

                    add_quarantine(
                        source_name,
                        "Community ID outside C001-C014",
                        invalid_count
                    )

                    # Remove invalid community records
                    df = df.loc[
                        ~invalid_communities
                    ].copy()

            # ------------------------------------------------
            # SAVE SILVER TABLE
            # ------------------------------------------------

            con.register(
                "silver_input",
                df
            )

            silver_table = (
                f"silver_{source_name}"
            )

            con.execute(
                f"""
                CREATE OR REPLACE TABLE {silver_table}
                AS
                SELECT *
                FROM silver_input
                """
            )

            # Save Parquet
            parquet_path = (
                SILVER_DIR /
                f"{source_name}.parquet"
            )

            df.to_parquet(
                parquet_path,
                index=False
            )

            add_log(
                source_name,
                "Silver",
                "PROCESSED",
                len(df),
                f"Cleaned {original_rows:,} rows"
            )

            print(
                f"[SILVER] {source_name}: "
                f"{len(df):,} rows"
            )

        except Exception as e:

            add_log(
                source_name,
                "Silver",
                "REJECTED",
                0,
                str(e)
            )

            print(
                f"[SILVER ERROR] "
                f"{source_name}: {e}"
            )


# ============================================================
# 6. GOLD LAYER
# ============================================================

def create_gold(con):

    print("\n" + "=" * 60)
    print("GOLD LAYER")
    print("=" * 60)

    # --------------------------------------------------------
    # COMMUNITY DIMENSION
    # --------------------------------------------------------

    con.execute(
        """
        CREATE OR REPLACE TABLE dim_community AS

        SELECT
            community_id,

            CASE
                WHEN community_id IN
                    ('C001','C002','C003','C004','C005')
                    THEN 'Oregon'

                WHEN community_id IN
                    ('C006','C007','C008','C009')
                    THEN 'Arizona'

                WHEN community_id IN
                    ('C010','C011','C012','C013','C014')
                    THEN 'Texas'
            END AS state,

            CASE
                WHEN community_id IN
                    ('C001','C002','C003','C004','C005')
                    THEN 'Pacific Northwest'

                WHEN community_id IN
                    ('C006','C007','C008','C009')
                    THEN 'Southwest'

                WHEN community_id IN
                    ('C010','C011','C012','C013','C014')
                    THEN 'South'
            END AS region

        FROM (
            SELECT DISTINCT community_id
            FROM silver_pcc_residents

            UNION

            SELECT DISTINCT community_id
            FROM silver_yardi_units

            UNION

            SELECT DISTINCT community_id
            FROM silver_pcc_incidents

            UNION

            SELECT DISTINCT community_id
            FROM silver_yardi_leases

            UNION

            SELECT DISTINCT community_id
            FROM silver_adp_shifts

            UNION

            SELECT DISTINCT community_id
            FROM silver_gbp_reviews

            UNION

            SELECT DISTINCT community_id
            FROM silver_hubspot_leads
        )

        WHERE community_id IS NOT NULL
        """
    )

    # --------------------------------------------------------
    # DATE DIMENSION
    # --------------------------------------------------------

    con.execute(
        """
        CREATE OR REPLACE TABLE dim_date AS

        SELECT

            date_value AS date,

            EXTRACT(
                YEAR FROM date_value
            ) AS year,

            EXTRACT(
                MONTH FROM date_value
            ) AS month_number,

            STRFTIME(
                date_value,
                '%B'
            ) AS month_name,

            DATE_TRUNC(
                'month',
                date_value
            ) AS month_start

        FROM generate_series(
            DATE '2025-01-01',
            DATE '2025-12-31',
            INTERVAL '1 day'
        ) AS t(date_value)
        """
    )

    # --------------------------------------------------------
    # RESIDENT DIMENSION
    # --------------------------------------------------------

    con.execute(
        """
        CREATE OR REPLACE TABLE dim_resident AS

        SELECT

            resident_id,

            ANY_VALUE(community_id)
                AS community_id,

            ANY_VALUE(first_name)
                AS first_name,

            ANY_VALUE(last_name)
                AS last_name,

            ANY_VALUE(dob)
                AS dob,

            ANY_VALUE(gender)
                AS gender,

            MIN(admit_date)
                AS admit_date,

            MAX(discharge_date)
                AS discharge_date

        FROM silver_pcc_residents

        GROUP BY resident_id
        """
    )

    # --------------------------------------------------------
    # UNIT DIMENSION
    # --------------------------------------------------------

    con.execute(
        """
        CREATE OR REPLACE TABLE dim_unit AS

        SELECT

            unit_id,

            ANY_VALUE(community_id)
                AS community_id,

            ANY_VALUE(unit_type)
                AS unit_type

        FROM silver_yardi_units

        GROUP BY unit_id
        """
    )

    # --------------------------------------------------------
    # CARE LEVEL DIMENSION
    # --------------------------------------------------------

    con.execute(
        """
        CREATE OR REPLACE TABLE dim_care_level AS

        SELECT *
        FROM (
            VALUES
                ('Independent Living'),
                ('Assisted Living'),
                ('Memory Care')
        ) AS t(care_level)
        """
    )

    # --------------------------------------------------------
    # RESIDENT MONTH FACT
    # --------------------------------------------------------

    con.execute(
        """
        CREATE OR REPLACE TABLE fact_resident_month AS

        SELECT

            resident_id,

            community_id,

            care_level,

            acuity_score,

            REGEXP_EXTRACT(
                source_file,
                '_(\\d{4}_\\d{2})',
                1
            ) AS snapshot_month,

            STRPTIME(
                REGEXP_EXTRACT(
                    source_file,
                    '_(\\d{4}_\\d{2})',
                    1
                ) || '-01',
                '%Y_%m-%d'
            )::DATE AS snapshot_date

        FROM silver_pcc_residents
        """
    )

    # --------------------------------------------------------
    # INCIDENT FACT
    # --------------------------------------------------------

    con.execute(
        """
        CREATE OR REPLACE TABLE fact_incident AS

        SELECT

            incident_id,
            resident_id,
            community_id,
            incident_date,
            incident_type,
            severity,
            reported_by

        FROM silver_pcc_incidents
        """
    )

    # --------------------------------------------------------
    # LEASE FACT
    # --------------------------------------------------------

    con.execute(
        """
        CREATE OR REPLACE TABLE fact_lease AS

        SELECT

            lease_id,
            resident_id,
            unit_id,
            community_id,
            move_in_date,
            move_out_date,
            move_out_reason,
            monthly_rate

        FROM silver_yardi_leases
        """
    )

    # --------------------------------------------------------
    # ADP SHIFT FACT
    # --------------------------------------------------------

    con.execute(
        """
        CREATE OR REPLACE TABLE fact_shift AS

        SELECT

            shift_id,
            community_id,
            employee_id,
            role,
            shift_date,
            hours_worked,
            hourly_rate,

            hours_worked * hourly_rate
                AS labor_cost

        FROM silver_adp_shifts
        """
    )

    # --------------------------------------------------------
    # REVIEW FACT
    # --------------------------------------------------------

    con.execute(
        """
        CREATE OR REPLACE TABLE fact_review AS

        SELECT

            review_id,
            community_id,
            review_date,
            rating,
            review_text,
            response_text,
            responded_at

        FROM silver_gbp_reviews
        """
    )

    # --------------------------------------------------------
    # LEAD FACT
    # --------------------------------------------------------

    con.execute(
        """
        CREATE OR REPLACE TABLE fact_lead AS

        SELECT

            lead_id,
            community_id,
            lead_source,
            created_date,
            tour_date,
            deposit_date,
            move_in_date,
            status,
            lost_reason

        FROM silver_hubspot_leads
        """
    )

    # --------------------------------------------------------
    # UNIT SNAPSHOT FACT
    # --------------------------------------------------------

    con.execute(
        """
        CREATE OR REPLACE TABLE fact_unit_snapshot AS

        SELECT

            unit_id,
            community_id,
            unit_type,
            monthly_rent,
            snapshot_date

        FROM silver_yardi_units
        """
    )

    # --------------------------------------------------------
    # EXPORT GOLD TABLES TO PARQUET
    # --------------------------------------------------------

    gold_tables = [
        "dim_community",
        "dim_date",
        "dim_resident",
        "dim_unit",
        "dim_care_level",
        "fact_resident_month",
        "fact_incident",
        "fact_lease",
        "fact_shift",
        "fact_review",
        "fact_lead",
        "fact_unit_snapshot"
    ]

    for table_name in gold_tables:

        output_path = (
            GOLD_DIR /
            f"{table_name}.parquet"
        )

        df = con.execute(
            f"SELECT * FROM {table_name}"
        ).df()

        df.to_parquet(
            output_path,
            index=False
        )

        print(
            f"[GOLD] {table_name}: "
            f"{len(df):,} rows"
        )

    print(
        "\n[GOLD] Star schema created successfully"
    )


# ============================================================
# 7. SAVE LOGS
# ============================================================

def save_logs():

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    run_log_file = (
        LOG_DIR /
        f"pipeline_run_{timestamp}.csv"
    )

    quarantine_file = (
        LOG_DIR /
        f"quarantine_log_{timestamp}.csv"
    )

    pd.DataFrame(
        run_log
    ).to_csv(
        run_log_file,
        index=False
    )

    pd.DataFrame(
        quarantine_log
    ).to_csv(
        quarantine_file,
        index=False
    )

    print(
        f"\nRun log: {run_log_file}"
    )

    print(
        f"Quarantine log: {quarantine_file}"
    )


# ============================================================
# 8. MAIN PIPELINE
# ============================================================

def main():

    print("\n" + "=" * 60)
    print(" PINEWOOD SENIOR LIVING DATA PIPELINE")
    print("=" * 60)

    print(
        f"Run timestamp: {RUN_TIMESTAMP}"
    )

    con = duckdb.connect(
        str(DB_PATH)
    )

    try:

        create_bronze(con)

        create_silver(con)

        create_gold(con)

        save_logs()

        print("\n" + "=" * 60)
        print(
            " PIPELINE COMPLETED SUCCESSFULLY"
        )
        print("=" * 60)

    except Exception as e:

        print("\n" + "=" * 60)
        print(" PIPELINE FAILED")
        print("=" * 60)

        print(e)

        raise

    finally:

        con.close()


if __name__ == "__main__":
    main()