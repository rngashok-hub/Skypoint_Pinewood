-- ============================================================
-- PINEWOOD SENIOR LIVING
-- BUSINESS SQL QUERIES
-- ============================================================


-- ============================================================
-- QUERY 1
-- MONTHLY OCCUPANCY RATE BY COMMUNITY
-- ============================================================

WITH monthly_occupied AS (

    SELECT
        community_id,
        snapshot_date AS month_start,
        COUNT(DISTINCT resident_id) AS occupied_residents

    FROM fact_resident_month

    GROUP BY
        community_id,
        snapshot_date
),

monthly_units AS (

    SELECT
        community_id,
        snapshot_date AS month_start,
        COUNT(DISTINCT unit_id) AS total_units

    FROM fact_unit_snapshot

    GROUP BY
        community_id,
        snapshot_date
)

SELECT

    u.community_id,

    u.month_start,

    COALESCE(
        o.occupied_residents,
        0
    ) AS occupied_residents,

    u.total_units,

    ROUND(
        COALESCE(
            o.occupied_residents,
            0
        ) * 100.0
        /
        NULLIF(
            u.total_units,
            0
        ),
        2
    ) AS occupancy_rate_pct

FROM monthly_units u

LEFT JOIN monthly_occupied o

    ON u.community_id = o.community_id

    AND u.month_start = o.month_start

ORDER BY
    u.month_start,
    u.community_id;


-- ============================================================
-- QUERY 2
-- TOP 3 MOVE-OUT REASONS BY COMMUNITY
-- ============================================================

WITH moveouts AS (

    SELECT

        community_id,

        move_out_reason,

        COUNT(*) AS move_out_count

    FROM fact_lease

    WHERE move_out_date IS NOT NULL

    GROUP BY

        community_id,

        move_out_reason
),

community_totals AS (

    SELECT

        community_id,

        SUM(move_out_count) AS total_moveouts

    FROM moveouts

    GROUP BY community_id
),

ranked_reasons AS (

    SELECT

        m.community_id,

        m.move_out_reason,

        m.move_out_count,

        t.total_moveouts,

        ROUND(

            m.move_out_count * 100.0

            /

            NULLIF(
                t.total_moveouts,
                0
            ),

            2

        ) AS pct_of_moveouts,

        ROW_NUMBER() OVER (

            PARTITION BY m.community_id

            ORDER BY

                m.move_out_count DESC,

                m.move_out_reason

        ) AS reason_rank

    FROM moveouts m

    INNER JOIN community_totals t

        ON m.community_id = t.community_id
)

SELECT

    community_id,

    reason_rank,

    move_out_reason,

    move_out_count,

    total_moveouts,

    pct_of_moveouts

FROM ranked_reasons

WHERE reason_rank <= 3

ORDER BY

    community_id,

    reason_rank;


-- ============================================================
-- ============================================================
-- QUERY 3
-- INCIDENT RATE PER 100 RESIDENT-DAYS
-- BY COMMUNITY AND CARE LEVEL
-- ============================================================

WITH resident_month AS (

    SELECT DISTINCT

        resident_id,
        community_id,
        care_level,
        snapshot_date AS month_start,
        LAST_DAY(snapshot_date) AS month_end

    FROM fact_resident_month
),

resident_days AS (

    SELECT

        r.community_id,
        r.care_level,
        r.month_start,

        SUM(

            GREATEST(

                0,

                DATE_DIFF(

                    'day',

                    GREATEST(

                        CAST(d.admit_date AS DATE),
                        r.month_start

                    ),

                    LEAST(

                        COALESCE(

                            CAST(d.discharge_date AS DATE),

                            r.month_end + INTERVAL '1 day'

                        ),

                        r.month_end + INTERVAL '1 day'

                    )

                )

            )

        ) AS resident_days

    FROM resident_month r

    INNER JOIN dim_resident d

        ON r.resident_id = d.resident_id

    WHERE

        CAST(d.admit_date AS DATE)
            <= r.month_end

        AND (

            d.discharge_date IS NULL

            OR CAST(d.discharge_date AS DATE)
                >= r.month_start

        )

    GROUP BY

        r.community_id,
        r.care_level,
        r.month_start
),

incident_by_care_level AS (

    SELECT

        i.community_id,

        r.care_level,

        DATE_TRUNC(
            'month',
            i.incident_date
        )::DATE AS month_start,

        COUNT(*) AS incident_count

    FROM fact_incident i

    INNER JOIN fact_resident_month r

        ON i.resident_id = r.resident_id

        AND i.community_id = r.community_id

        AND DATE_TRUNC(
            'month',
            i.incident_date
        )::DATE = r.snapshot_date

    GROUP BY

        i.community_id,

        r.care_level,

        DATE_TRUNC(
            'month',
            i.incident_date
        )::DATE
)

SELECT

    r.community_id,

    r.care_level,

    r.month_start,

    COALESCE(
        i.incident_count,
        0
    ) AS incident_count,

    r.resident_days,

    ROUND(

        COALESCE(
            i.incident_count,
            0
        ) * 100.0

        /

        NULLIF(
            r.resident_days,
            0
        ),

        2

    ) AS incidents_per_100_resident_days

FROM resident_days r

LEFT JOIN incident_by_care_level i

    ON r.community_id = i.community_id

    AND r.care_level = i.care_level

    AND r.month_start = i.month_start

ORDER BY

    r.month_start,

    r.community_id,

    r.care_level;