SET STATISTICS TIME ON; SET STATISTICS IO ON;
DECLARE @Start date='20160501',@End date='20160601';
SELECT COUNT_BIG(*) UnpickedLines,COUNT(DISTINCT o.OrderID) Orders,SUM(CONVERT(bigint,ol.Quantity)-ol.PickedQuantity) UnpickedUnits FROM Sales.Orders o JOIN Sales.OrderLines ol ON ol.OrderID=o.OrderID WHERE o.OrderDate>=@Start AND o.OrderDate<@End AND ol.PickedQuantity<ol.Quantity;
SELECT o.OrderID,ol.OrderLineID,ol.StockItemID,o.OrderDate,ol.Quantity,ol.PickedQuantity,CONVERT(bigint,ol.Quantity)-ol.PickedQuantity UnpickedUnits FROM Sales.Orders o JOIN Sales.OrderLines ol ON ol.OrderID=o.OrderID WHERE o.OrderDate>=@Start AND o.OrderDate<@End AND ol.PickedQuantity<ol.Quantity ORDER BY o.OrderID,ol.OrderLineID;
SET STATISTICS TIME OFF; SET STATISTICS IO OFF;

