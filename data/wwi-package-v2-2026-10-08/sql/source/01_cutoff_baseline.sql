DECLARE @start date = '20160501';
DECLARE @end date = '20160601';

WITH line_totals AS (
  SELECT OrderID,
         COUNT_BIG(*) AS line_count,
         SUM(CAST(Quantity AS bigint)) AS ordered_units,
         SUM(CASE WHEN Quantity > PickedQuantity THEN 1 ELSE 0 END)
           AS underpicked_lines,
         SUM(CASE WHEN Quantity > PickedQuantity
                  THEN CAST(Quantity AS bigint) - CAST(PickedQuantity AS bigint)
                  ELSE CAST(0 AS bigint) END) AS underpicked_units
  FROM Sales.OrderLines
  GROUP BY OrderID
)
SELECT o.OrderDate,
       COUNT_BIG(*) AS orders_created,
       SUM(CASE WHEN l.underpicked_lines > 0 THEN 1 ELSE 0 END)
         AS orders_with_underpicked_lines,
       SUM(l.underpicked_lines) AS underpicked_lines,
       SUM(l.underpicked_units) AS underpicked_units,
       SUM(l.ordered_units) AS ordered_units
FROM Sales.Orders AS o
JOIN line_totals AS l ON l.OrderID = o.OrderID
WHERE o.OrderDate >= @start AND o.OrderDate < @end
GROUP BY o.OrderDate
ORDER BY o.OrderDate;
