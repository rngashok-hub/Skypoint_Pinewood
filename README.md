# Pinewood Senior Living - FDE Assessment

## 1. Executive Summary

This project implements an end-to-end analytics solution for Pinewood Senior Living using six months of operational data from five source systems:

- PointClickCare (PCC)
- Yardi
- ADP
- Google Business Profile (GBP)
- HubSpot

The solution follows a Bronze -> Silver -> Gold architecture and produces a Power BI-ready Gold star schema.

The solution includes:

- Python ingestion and transformation pipeline
- DuckDB analytical database
- Parquet Gold-layer outputs
- Gold star schema for Power BI
- SQL business analysis
- COO executive dashboard
- Dynamic Row-Level Security (RLS)
- Data-quality validation and quarantine
- Pipeline run and quarantine logs


## 2. Architecture

```text
Source CSV Files
      |
      v
+----------------------+
|       BRONZE         |
| Raw source data      |
| + ingestion metadata |
+----------------------+
      |
      v
+----------------------+
|       SILVER         |
| Cleaned and typed    |
| Standardized values  |
| Deduplication        |
| Validation           |
+----------------------+
      |
      v
+----------------------+
|        GOLD          |
| Star schema          |
| Dimensions + Facts   |
+----------------------+
      |
      +------------------+
      |                  |
      v                  v
   DuckDB             Parquet
      |                  |
      +--------+---------+
               |
               v
           Power BI
               |
               v
      COO Executive Dashboard
               |
               v
              RLS
3. Project Structure
Skypoint_Pinewood/
|
+-- Data/                       Source CSV files
|
+-- pipeline/
|   +-- run_pipeline.py        Main pipeline
|
+-- sql/
|   +-- 01_schema_ddl.sql      Gold schema and grain notes
|   +-- 02_business_queries.sql Business analysis queries
|
+-- powerbi/
|   +-- Pinewood_FDE.pbix      Power BI report
|
+-- communication/
|   +-- email_to_karen.md      Access request
|
+-- bronze/                     Bronze outputs
+-- silver/                     Silver outputs
+-- gold/                       Gold DuckDB and Parquet outputs
+-- quarantine/                 Quarantined records
+-- logs/                       Pipeline and quarantine logs
|
+-- inspection.txt              Source inspection results
+-- schema_report.txt          Schema inspection results
+-- README.md
4. Source Data

The supplied dataset contains 48 CSV files covering six months from January through June 2025.

There are eight source table types:

ADP shifts
Google Business Profile reviews
HubSpot leads
PCC care history
PCC incidents
PCC residents
Yardi leases
Yardi units

Each source contains six monthly exports.

5. Pipeline

The pipeline is implemented in:

pipeline/run_pipeline.py

The complete pipeline can be executed with one command:

python pipeline\run_pipeline.py

The pipeline is designed to be rerunnable without repeatedly appending the same monthly source data.

Bronze Layer

Bronze preserves source data with minimal transformation.

The pipeline:

Reads monthly CSV exports
Combines monthly files by source
Preserves source-level records
Adds ingestion metadata
Allows monthly schema differences
Silver Layer

Silver applies data-quality and standardization rules including:

Date standardization
Numeric type conversion
Care-level standardization
Duplicate handling
ADP hourly-rate parsing
Community ID validation
Acuity-score validation
Schema-drift handling

Invalid records are quarantined where appropriate instead of being silently discarded.

Gold Layer

The Gold layer provides a Power BI-ready analytical star schema.

It contains:

Dimensions
dim_community
dim_date
dim_resident
dim_unit
dim_care_level
Facts
fact_resident_month
fact_incident
fact_lease
fact_shift
fact_review
fact_lead
fact_unit_snapshot
6. Final Pipeline Validation

The final pipeline execution completed successfully.

Bronze
Table	Rows
adp_shifts	68,071
gbp_reviews	424
hubspot_leads	830
pcc_care_history	303
pcc_incidents	411
pcc_residents	4,152
yardi_leases	346
yardi_units	5,490
Silver
Table	Rows
adp_shifts	68,071
gbp_reviews	424
hubspot_leads	830
pcc_care_history	303
pcc_incidents	411
pcc_residents	4,152
yardi_leases	346
yardi_units	5,460
Gold
Table	Rows
dim_community	14
dim_date	365
dim_resident	823
dim_unit	910
dim_care_level	3
fact_resident_month	4,152
fact_incident	411
fact_lease	346
fact_shift	68,071
fact_review	424
fact_lead	830
fact_unit_snapshot	5,460

The pipeline also generated a run log and quarantine log.

7. Gold Star Schema
dim_community

Grain: one row per community.

Columns include:

community_id
state
region

The region attribute is used for Regional Director RLS.

dim_date

Grain: one row per calendar date.

Columns include:

date
year
month_number
month_name
month_start
dim_resident

Grain: one row per resident.

Contains:

resident_id
community_id
admit_date
discharge_date
resident attributes
dim_unit

Grain: one row per unit.

Contains:

unit_id
community_id
unit_type
dim_care_level

Grain: one row per canonical care level.

Canonical values:

Independent Living
Assisted Living
Memory Care
fact_resident_month

Grain: one resident snapshot per month.

Contains:

resident_id
community_id
care_level
acuity_score
snapshot_date
snapshot_month
fact_incident

Grain: one incident event.

Contains:

incident_id
resident_id
community_id
incident_date
incident_type
severity
fact_lease

Grain: one lease transaction.

Contains:

lease_id
resident_id
unit_id
community_id
move_in_date
move_out_date
move_out_reason
monthly_rate
fact_shift

Grain: one employee shift.

Contains:

shift_id
employee_id
community_id
role
shift_date
hours_worked
hourly_rate
labor_cost
fact_review

Grain: one Google Business Profile review.

Contains:

review_id
community_id
review_date
rating
fact_lead

Grain: one HubSpot lead.

Contains:

lead_id
community_id
lead_source
created_date
tour_date
deposit_date
move_in_date
status
lost_reason
fact_unit_snapshot

Grain: one unit per monthly snapshot.

Contains:

unit_id
community_id
unit_type
monthly_rent
snapshot_date
8. Power BI Model

The Power BI model follows a star-schema approach.

Dimension tables filter fact tables using one-to-many, single-direction relationships.

Fact-to-fact relationships were avoided to reduce ambiguity and maintain a clean analytical model.

Key relationships include:

dim_community
    |
    +-- fact_resident_month
    +-- fact_incident
    +-- fact_lease
    +-- fact_shift
    +-- fact_review
    +-- fact_lead
    +-- fact_unit_snapshot

dim_resident
    |
    +-- fact_resident_month
    +-- fact_incident
    +-- fact_lease

dim_unit
    |
    +-- fact_unit_snapshot
    +-- fact_lease

dim_care_level
    |
    +-- fact_resident_month

dim_date
    |
    +-- fact_resident_month
    +-- fact_incident
    +-- fact_lease
    +-- fact_shift
    +-- fact_review
    +-- fact_lead
    +-- fact_unit_snapshot
9. DAX Measures
Occupied Residents
Occupied Residents =
DISTINCTCOUNT(
    fact_resident_month[resident_id]
)
Total Units
Total Units =
DISTINCTCOUNT(
    fact_unit_snapshot[unit_id]
)
Current Occupancy %
Current Occupancy % =
DIVIDE(
    [Occupied Residents],
    [Total Units],
    BLANK()
)
Move-Outs
Move-Outs =
CALCULATE(
    DISTINCTCOUNT(fact_lease[resident_id]),
    NOT ISBLANK(fact_lease[move_out_date])
)
Average Occupied Residents - 90 Days
Avg Occupied Residents 90D =
AVERAGEX(
    VALUES(dim_date[month_start]),
    CALCULATE(
        [Occupied Residents]
    )
)
Trailing 90-Day Move-Out Rate %
Trailing 90-Day Move-Out Rate % =
VAR DataEndDate =
    CALCULATE(
        MAX(fact_lease[move_out_date]),
        ALL(fact_lease)
    )
VAR EndDate =
    MIN(
        MAX(dim_date[date]),
        DataEndDate
    )
VAR StartDate =
    EndDate - 89
VAR MoveOuts90D =
    CALCULATE(
        [Move-Outs],
        DATESBETWEEN(
            dim_date[date],
            StartDate,
            EndDate
        )
    )
VAR AvgOccupied90D =
    CALCULATE(
        [Avg Occupied Residents 90D],
        DATESBETWEEN(
            dim_date[date],
            StartDate,
            EndDate
        )
    )
RETURN
    DIVIDE(
        MoveOuts90D,
        AvgOccupied90D,
        BLANK()
    )
Resident Days
Resident Days =
SUMX(
    fact_resident_month,
    VAR MonthStart =
        fact_resident_month[snapshot_date]
    VAR MonthEnd =
        EOMONTH(MonthStart, 0)
    VAR AdmitDate =
        RELATED(dim_resident[admit_date])
    VAR DischargeDate =
        RELATED(dim_resident[discharge_date])
    VAR StartDate =
        MAX(AdmitDate, MonthStart)
    VAR EndDate =
        MIN(
            COALESCE(DischargeDate, MonthEnd + 1),
            MonthEnd + 1
        )
    RETURN
        MAX(
            0,
            DATEDIFF(StartDate, EndDate, DAY)
        )
)
Incident Count
Incident Count =
VAR ResidentsInContext =
    CALCULATETABLE(
        VALUES(fact_resident_month[resident_id])
    )
RETURN
    CALCULATE(
        COUNTROWS(fact_incident),
        TREATAS(
            ResidentsInContext,
            fact_incident[resident_id]
        )
    )
Incident Rate per 100 Resident-Days
Incident Rate per 100 Resident-Days =
DIVIDE(
    [Incident Count],
    [Resident Days],
    BLANK()
) * 100
Occupancy Month-over-Month %
Occupancy MoM % =
VAR CurrentOccupancy =
    [Current Occupancy %]
VAR PreviousMonthOccupancy =
    CALCULATE(
        [Current Occupancy %],
        DATEADD(
            dim_date[date],
            -1,
            MONTH
        )
    )
RETURN
    IF(
        ISBLANK(PreviousMonthOccupancy),
        BLANK(),
        CurrentOccupancy - PreviousMonthOccupancy
    )
10. SQL Business Analysis

Business SQL is located in:

sql/02_business_queries.sql

The required analyses are:

Monthly occupancy rate by community.
Top three move-out reasons by community over the six-month period.
Incident rate per 100 resident-days by community and care level.

Schema documentation and Gold grain notes are located in:

sql/01_schema_ddl.sql
11. COO Executive Dashboard

The Power BI executive dashboard is designed for COO-level operational monitoring.

The dashboard contains:

Current Occupancy
Trailing 90-Day Move-Out Rate
Incident Rate per 100 Resident-Days
Occupied Residents
Monthly Occupancy Trend
Top 3 Move-Out Reasons
Incident Rate by Care Level
Region filter
Community filter
Reporting Period filter

The reporting period is January-June 2025, matching the six months of source data.

Final Dashboard KPI Values

The dashboard displays:

Current Occupancy: 90.44%
Trailing 90-Day Move-Out Rate: 7.24%
Incident Rate per 100 Resident-Days: 0.34
Occupied Residents: 823
12. Row-Level Security

Two RLS roles were implemented.

Regional Director

The Regional Director role determines the user's region from the security mapping table.

VAR UserRegion =
    LOOKUPVALUE(
        Security_Regional[Region],
        Security_Regional[Email],
        USERPRINCIPALNAME()
    )
RETURN
    dim_community[region] = UserRegion
Community Executive Director

The Community Executive Director role determines the user's community from the security mapping table.

VAR UserCommunity =
    LOOKUPVALUE(
        Security_Community[community_id],
        Security_Community[Email],
        USERPRINCIPALNAME()
    )
RETURN
    dim_community[community_id] = UserCommunity
RLS Validation

Both roles were tested using Power BI Desktop's View As functionality.

The Community Executive Director role was tested using:

exec.c001@pinewood.com

The test restricted the report to community C001.

The Regional Director role was also tested and confirmed to restrict data to the user's assigned region.

13. Data Quality and Anomalies
1. Care-Level Naming Variants

Source data contains multiple representations of care levels.

Examples include:

IL
Independent
Independent Living
AL
Assisted
Assisted Living
Memory-related variants

Handling: values were standardized to:

Independent Living
Assisted Living
Memory Care

Reason: ensures consistent grouping across source systems.

2. ADP Hourly Rate Format

The ADP hourly_rate field contains dictionary-like string values rather than a directly usable numeric value.

Handling: the numeric hourly rate is extracted during Silver processing.

Reason: enables reliable numerical analysis and labor-cost calculations.

3. PCC Schema Drift

The April PCC resident export contains an additional:

mobility_status

column.

The other monthly resident exports do not contain this field.

Handling: Bronze ingestion uses schema-tolerant concatenation so monthly schema differences do not stop the pipeline.

Reason: source systems can introduce additional fields without causing the entire pipeline to fail.

4. Invalid Acuity Scores

Some PCC resident records contain acuity scores outside the expected 1-10 range.

Handling: invalid acuity values are identified and quarantined rather than being treated as valid analytical values.

Reason: prevents invalid values from affecting downstream reporting while preserving the records for investigation.

5. Invalid Community IDs

Some records contain community IDs outside the expected Pinewood community range.

Handling: invalid community records are quarantined and excluded from the analytical Silver/Gold layers.

Reason: prevents orphan records from entering the dimensional model.

6. Occupancy Above 100%

Community C012 reports the following for June 2025:

Occupied residents: 66
Total units: 65
Calculated occupancy: 101.54%

Handling: the value is retained rather than artificially capped at 100% and is surfaced as a data-quality issue.

Reason: changing the value would hide the underlying source-data issue. The client should validate the business reason for the discrepancy.

14. Quarantine and Logging

Invalid records are preserved in the quarantine area where appropriate.

The pipeline generates:

logs/pipeline_run_<timestamp>.csv

and:

logs/quarantine_log_<timestamp>.csv

The quarantine approach provides an audit trail for data-quality issues rather than silently dropping records.

15. Rerun / Idempotency

The pipeline can be rerun using:

python pipeline\run_pipeline.py

Monthly files are grouped by source and rebuilt into the analytical layers.

This prevents repeated execution from continuously appending the same monthly data.

The final validation run completed successfully with:

68,071 ADP shift records
411 incident records
346 lease records
823 residents
910 units
14 communities

The final DuckDB database contains the expected Bronze, Silver and Gold tables with no temporary silver_df table.

16. Design Trade-Offs
DuckDB + Parquet

DuckDB provides a lightweight local analytical database suitable for the assessment without requiring a cloud database.

Parquet provides portable analytical outputs that can be consumed by Power BI.

Rebuild-Based Processing

The assessment implementation rebuilds the analytical layers from the available monthly source exports.

This provides deterministic reruns and prevents duplicate accumulation.

A production implementation could move to incremental processing using reliable source-system watermarks or change tracking.

Quarantine Instead of Silent Deletion

Invalid records are preserved through quarantine outputs where appropriate.

This supports investigation and provides transparency into data-quality issues.

Schema-Tolerant Ingestion

The pipeline does not assume every monthly export has exactly the same schema.

This allows source systems to introduce additional fields without causing the entire pipeline to fail.

17. Validation Summary

The following were validated:

48 monthly CSV files processed.
Five source systems represented.
Bronze layer successfully created.
Silver layer successfully cleaned and standardized.
Gold star schema successfully created.
14 communities represented.
823 residents represented.
910 units represented.
411 incidents represented.
346 leases represented.
Required SQL analyses created.
Power BI connected successfully to Gold Parquet outputs.
Current Occupancy measure validated.
Trailing 90-Day Move-Out Rate validated.
Incident Rate per 100 Resident-Days validated.
Occupancy Month-over-Month time intelligence validated.
Regional Director RLS validated.
Community Executive Director RLS validated.
COO dashboard completed.
Data-quality anomalies identified and surfaced.
18. How to Run

From the project root:

.venv\Scripts\activate
python pipeline\run_pipeline.py

The pipeline creates or refreshes the analytical layers and generates operational logs.

19. Communication

The access request communication is located at:

communication/email_to_karen.md

The communication is addressed to Karen Mills, Director of IT, and requests the required source-system access for a production implementation.

20. Walkthrough

Walkthrough recording:

[View the assessment walkthrough video](https://drive.google.com/file/d/12JaNlhCOUPPXp3B7fcQDDojclFWI31Td/view?usp=drive_link)

The walkthrough should cover:

Solution architecture
Bronze, Silver and Gold processing
Live pipeline execution
Pipeline code structure
Gold star schema
SQL business queries
Power BI dashboard
DAX measures
RLS implementation and View As testing
Selected data-quality anomalies
Design trade-offs
21. Submission Contents

The final project contains:

Python pipeline
SQL schema documentation
SQL business queries
Power BI PBIX
Communication artifact
README documentation
Source data
Bronze/Silver/Gold outputs
Quarantine outputs
Pipeline logs

No production credentials or secrets are included in the project.