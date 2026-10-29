-- Default scenario: 15 hours; AUD 2250 monthly capacity; AUD 27000 first-year value.
SELECT 20 * (1.0 - 0.25) AS monthly_hours_released,
       20 * (1.0 - 0.25) * 150 AS monthly_capacity_value_aud,
       12 * (20 * (1.0 - 0.25) * 150 - 0) - 0 AS first_year_net_value_aud;
