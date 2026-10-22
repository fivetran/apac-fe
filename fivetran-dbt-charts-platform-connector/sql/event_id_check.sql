-- Expected result: zero rows. Payload selection assumes LOG.ID identifies one event.
SELECT ID, COUNT(*) AS key_rows FROM NAAG_POSTGRES.NAAG_FIVETRAN_LOG.LOG GROUP BY ID HAVING COUNT(*) > 1 OR ID IS NULL LIMIT 20;
