from __future__ import annotations
import datetime
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
VERSION='wwi-data-v1-2026-10-08'
Scenario=Literal['base','no_incoming_v1']
DateBasis=Literal['order_date','expected_delivery_date','picking_completed_time','purchase_order_date','invoice_date','confirmed_delivery_time','none']
class Filters(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    customer_id:int|None=None
    stock_item_id:int|None=None
    supplier_id:int|None=None
    stock_group_id:int|None=None
    order_id:int|None=None
    order_line_id:int|None=None
    purchase_order_id:int|None=None
    purchase_line_id:int|None=None
    status:Literal['all','quantity-not-yet-picked','picking-incomplete','picking-complete','incoming','all-history']='all'
class Request(BaseModel):
    model_config=ConfigDict(extra='forbid')
    dataset_version:Literal['wwi-data-v1-2026-10-08']=VERSION
    scenario_id:Scenario='base'
    date_basis:DateBasis='order_date'
    start:datetime.date|None=None
    end:datetime.date|None=None
    filters:Filters=Field(default_factory=Filters)
    limit:int=Field(default=50,ge=1,le=200)
    offset:int=Field(default=0,ge=0,le=1000000)
    @model_validator(mode='after')
    def boundaries(self):
        if (self.start is None)!=(self.end is None):raise ValueError('Supply both start and end, inclusive/exclusive.')
        if self.start is not None:
            if self.date_basis=='none':raise ValueError('Undated holdings cannot accept date intervals.')
            if not datetime.date(2013,1,1)<=self.start<self.end<=datetime.date(2016,6,21):raise ValueError('Period outside verified archive domain, or empty interval.')
        for value in self.filters.model_dump().values():
            if isinstance(value,int) and not isinstance(value,bool) and value<=0:raise ValueError('Entity IDs must be positive integers.')
        return self
