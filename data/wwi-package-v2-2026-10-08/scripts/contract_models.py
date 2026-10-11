from __future__ import annotations
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
class Document(BaseModel):
    model_config=ConfigDict(extra='forbid')
    dataset_version:str
    scenario_id:str='base'
    supported_operations:list[str]
    context_propagation:dict[str,str]
class Measure(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str;name:str;business_question:str;grain:str;population:str;formula:str;unit:str
    currency:str|None=None
    date_basis:str
    supported_filters:list[str]
    null_behavior:str;comparison_rule:str;source_tables:list[str];query_file:str|None
    evidence_file:str;status:Literal['verified','candidate','rejected','blocked'];limitation:str
    tested_domain:list[dict]
class Filter(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str;views:list[str];field:str;date_basis:str|None;operators:list[str];default:str|None
    value_type:str;valid_enums:list[str];id_lookup:str|None;propagation:str;reset_rule:str
class Chart(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str;title:str;widget_id:str;measure_id:str;query_file:str;evidence_file:str
    axes:dict[str,str];sorting:list[str];comparison:str;drill_down:str;caption:str
class View(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str;route:str;url_parameters:list[str];widgets:list[str];detail_destinations:list[str];integration_status:str
class Widget(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str;type:str;view_id:str;query_id:str;measure_id:str|None;display_unit:str
    filters:list[str];record_links:list[str];loading:str;empty:str;error:str
class Measures(Document):items:list[Measure]
class Filters(Document):items:list[Filter]
class Charts(Document):items:list[Chart]
class Views(Document):items:list[View]
class Widgets(Document):items:list[Widget]
class Version(Document):
    contract_version:str;query_catalog_version:str;schema_version:str;supported_scenario_ids:list[str]
    # v2 additions (optional, so v0.1.0 documents still validate)
    package_version:str|None=None;documents:list[str]=[];money_published:str|None=None
MODELS={'measures':Measures,'filters':Filters,'charts':Charts,'views':Views,'widgets':Widgets,'contract_version':Version}
