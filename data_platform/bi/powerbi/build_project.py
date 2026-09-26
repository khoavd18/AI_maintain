"""Generate the source-controlled Power BI demo project.

The generator is intentionally deterministic: report/page/visual IDs and TMDL
lineage tags are derived from stable names. It accepts connection location but
never accepts or writes database credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PROJECT_NAME = "MaintenanceAnalytics"
DEFAULT_SERVER = "127.0.0.1:25432"
DEFAULT_DATABASE = "maintenance_copilot_benchmark_scale"
OUTPUT_ROOT = Path(__file__).resolve().parent / PROJECT_NAME
NAMESPACE = uuid.UUID("8d41c1dc-c7a5-43ca-aadb-56afe31c7759")

PBIP_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/pbip/"
    "pbipProperties/1.0.0/schema.json"
)
PLATFORM_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/"
    "platformProperties/2.0.0/schema.json"
)
PBIR_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/"
    "definitionProperties/2.0.0/schema.json"
)
PBISM_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/"
    "definitionProperties/1.0.0/schema.json"
)
REPORT_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/"
    "definition/report/3.3.0/schema.json"
)
VERSION_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/"
    "definition/versionMetadata/1.0.0/schema.json"
)
PAGES_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/"
    "definition/pagesMetadata/1.0.0/schema.json"
)
PAGE_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/"
    "definition/page/2.1.0/schema.json"
)
VISUAL_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/"
    "definition/visualContainer/2.9.0/schema.json"
)

NAVY = "#15324B"
BLUE = "#1F77B4"
TEAL = "#178F8F"
GREEN = "#2E8B57"
AMBER = "#D98900"
RED = "#C43D3D"
PURPLE = "#7257A5"
PAGE_BACKGROUND = "#F4F7FA"
CARD_BACKGROUND = "#FFFFFF"
BORDER = "#D9E2EA"
MUTED = "#5B6B7A"


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str
    source: str | None = None
    hidden: bool = False
    format_string: str | None = None


@dataclass(frozen=True)
class Measure:
    name: str
    expression: str
    format_string: str
    description: str


@dataclass(frozen=True)
class Table:
    name: str
    schema: str | None
    source_name: str | None
    columns: tuple[Column, ...]
    measures: tuple[Measure, ...] = ()
    native_sql: str | None = None


def stable_uuid(label: str) -> str:
    return str(uuid.uuid5(NAMESPACE, label))


def stable_hex(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()[:20]


def tmdl_name(value: str) -> str:
    if value.replace("_", "").isalnum() and " " not in value:
        return value
    return "'" + value.replace("'", "''") + "'"


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def m_text(value: str) -> str:
    return value.replace('"', '""')


def literal(value: str | bool | int | float, suffix: str | None = None) -> dict[str, Any]:
    if isinstance(value, bool):
        encoded = "true" if value else "false"
    elif isinstance(value, str):
        encoded = "'" + value.replace("'", "''") + "'"
    elif isinstance(value, int):
        encoded = f"{value}{suffix or 'D'}"
    else:
        encoded = f"{value}{suffix or 'D'}"
    return {"expr": {"Literal": {"Value": encoded}}}


def solid(color: str) -> dict[str, Any]:
    return {"solid": {"color": literal(color)}}


def source_ref(table: str) -> dict[str, Any]:
    return {"SourceRef": {"Entity": table}}


def column_field(table: str, column: str) -> dict[str, Any]:
    return {
        "Column": {
            "Expression": source_ref(table),
            "Property": column,
        }
    }


def measure_field(table: str, measure: str) -> dict[str, Any]:
    return {
        "Measure": {
            "Expression": source_ref(table),
            "Property": measure,
        }
    }


def projection(
    table: str,
    property_name: str,
    label: str,
    *,
    is_measure: bool,
    active: bool | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "field": (
            measure_field(table, property_name)
            if is_measure
            else column_field(table, property_name)
        ),
        "queryRef": f"{table}.{property_name}",
        "nativeQueryRef": label,
    }
    if active is not None:
        item["active"] = active
    return item


def position(x: int, y: int, width: int, height: int, order: int) -> dict[str, Any]:
    return {
        "x": x,
        "y": y,
        "z": order,
        "height": height,
        "width": width,
        "tabOrder": order,
    }


def common_vco(title: str | None = None) -> dict[str, Any]:
    vco: dict[str, Any] = {
        "background": [
            {
                "properties": {
                    "show": literal(True),
                    "color": solid(CARD_BACKGROUND),
                    "transparency": literal(0),
                }
            }
        ],
        "border": [
            {
                "properties": {
                    "show": literal(True),
                    "color": solid(BORDER),
                    "radius": literal(8),
                    "width": literal(1),
                }
            }
        ],
        "visualHeader": [{"properties": {"show": literal(False)}}],
        "padding": [
            {
                "properties": {
                    "top": literal(8),
                    "bottom": literal(8),
                    "left": literal(8),
                    "right": literal(8),
                }
            }
        ],
    }
    if title:
        vco["title"] = [
            {
                "properties": {
                    "show": literal(True),
                    "text": literal(title),
                    "fontColor": solid(NAVY),
                    "fontSize": literal(12),
                    "bold": literal(True),
                    "fontFamily": literal("Segoe UI Semibold"),
                    "heading": literal("Heading3"),
                }
            }
        ]
    return vco


def title_visual(page_key: str, text: str, subtitle: str) -> list[dict[str, Any]]:
    def textbox(key: str, value: str, y: int, height: int, size: str, color: str) -> dict[str, Any]:
        return {
            "$schema": VISUAL_SCHEMA,
            "name": stable_hex(f"{page_key}:{key}"),
            "position": position(24, y, 760, height, 10 if key == "title" else 20),
            "visual": {
                "visualType": "textbox",
                "objects": {
                    "general": [
                        {
                            "properties": {
                                "paragraphs": [
                                    {
                                        "textRuns": [
                                            {
                                                "value": value,
                                                "textStyle": {
                                                    "fontFamily": "Segoe UI Semibold",
                                                    "fontSize": size,
                                                    "color": color,
                                                },
                                            }
                                        ],
                                        "horizontalTextAlignment": "left",
                                    }
                                ]
                            }
                        }
                    ]
                },
                "visualContainerObjects": {
                    "background": [{"properties": {"show": literal(False)}}],
                    "border": [{"properties": {"show": literal(False)}}],
                    "visualHeader": [{"properties": {"show": literal(False)}}],
                    "padding": [
                        {
                            "properties": {
                                "top": literal(0),
                                "bottom": literal(0),
                                "left": literal(0),
                                "right": literal(0),
                            }
                        }
                    ],
                },
            },
        }

    return [
        textbox("title", text, 16, 40, "24px", NAVY),
        textbox("subtitle", subtitle, 56, 28, "11px", MUTED),
    ]


def slicer_visual(
    page_key: str,
    key: str,
    table: str,
    column: str,
    label: str,
    x: int,
    width: int,
    *,
    mode: str = "Dropdown",
) -> dict[str, Any]:
    vco = common_vco()
    return {
        "$schema": VISUAL_SCHEMA,
        "name": stable_hex(f"{page_key}:{key}"),
        "position": position(x, 16, width, 80, 100),
        "visual": {
            "visualType": "slicer",
            "query": {
                "queryState": {
                    "Values": {
                        "projections": [
                            projection(table, column, label, is_measure=False)
                        ]
                    }
                }
            },
            "objects": {
                "data": [{"properties": {"mode": literal(mode)}}],
                "header": [
                    {
                        "properties": {
                            "show": literal(True),
                            "text": literal(label),
                        }
                    }
                ],
            },
            "visualContainerObjects": vco,
        },
    }


def card_visual(
    page_key: str,
    key: str,
    table: str,
    measure: str,
    label: str,
    x: int,
    color: str,
    *,
    width: int = 240,
) -> dict[str, Any]:
    vco = common_vco()
    vco["border"][0]["properties"]["color"] = solid(color)
    return {
        "$schema": VISUAL_SCHEMA,
        "name": stable_hex(f"{page_key}:{key}"),
        "position": position(x, 104, width, 112, 200 + x),
        "visual": {
            "visualType": "cardVisual",
            "query": {
                "queryState": {
                    "Data": {
                        "projections": [
                            projection(table, measure, label, is_measure=True)
                        ]
                    }
                }
            },
            "objects": {
                "value": [
                    {
                        "properties": {
                            "fontSize": literal(24),
                            "fontColor": solid(color),
                            "bold": literal(True),
                        },
                        "selector": {"id": "default"},
                    }
                ],
                "label": [
                    {
                        "properties": {
                            "show": literal(True),
                            "text": literal(label),
                            "fontSize": literal(10),
                            "fontColor": solid(MUTED),
                            "textWrap": literal(True),
                        },
                        "selector": {"id": "default"},
                    }
                ],
                "outline": [
                    {
                        "properties": {"show": literal(False)},
                        "selector": {"id": "default"},
                    }
                ],
            },
            "visualContainerObjects": vco,
        },
    }


def chart_visual(
    page_key: str,
    key: str,
    visual_type: str,
    title: str,
    category: tuple[str, str, str],
    measures: list[tuple[str, str, str, str]],
    layout: tuple[int, int, int, int],
    *,
    sort_measure: tuple[str, str] | None = None,
    sort_direction: str = "Descending",
) -> dict[str, Any]:
    x, y, width, height = layout
    y_projections = [
        projection(table, measure, label, is_measure=True)
        for table, measure, label, _color in measures
    ]
    query: dict[str, Any] = {
        "queryState": {
            "Category": {
                "projections": [
                    projection(
                        category[0],
                        category[1],
                        category[2],
                        is_measure=False,
                        active=True,
                    )
                ]
            },
            "Y": {"projections": y_projections},
        }
    }
    if sort_measure:
        query["sortDefinition"] = {
            "sort": [
                {
                    "field": measure_field(sort_measure[0], sort_measure[1]),
                    "direction": sort_direction,
                }
            ],
            "isDefaultSort": True,
        }

    data_points = [
        {
            "properties": {"fill": solid(color)},
            "selector": {"metadata": f"{table}.{measure}"},
        }
        for table, measure, _label, color in measures
    ]
    objects: dict[str, Any] = {"dataPoint": data_points}

    return {
        "$schema": VISUAL_SCHEMA,
        "name": stable_hex(f"{page_key}:{key}"),
        "position": position(x, y, width, height, 2000 + x + y),
        "visual": {
            "visualType": visual_type,
            "query": query,
            "objects": objects,
            "visualContainerObjects": common_vco(title),
        },
    }


def table_visual(
    page_key: str,
    key: str,
    title: str,
    fields: list[tuple[str, str, str, bool]],
    layout: tuple[int, int, int, int],
    *,
    sort_measure: tuple[str, str] | None = None,
) -> dict[str, Any]:
    x, y, width, height = layout
    query: dict[str, Any] = {
        "queryState": {
            "Values": {
                "projections": [
                    projection(table, field, label, is_measure=is_measure)
                    for table, field, label, is_measure in fields
                ]
            }
        }
    }
    if sort_measure:
        query["sortDefinition"] = {
            "sort": [
                {
                    "field": measure_field(sort_measure[0], sort_measure[1]),
                    "direction": "Descending",
                }
            ],
            "isDefaultSort": True,
        }
    vco = common_vco(title)
    vco["stylePreset"] = [{"properties": {"name": literal("None")}}]
    return {
        "$schema": VISUAL_SCHEMA,
        "name": stable_hex(f"{page_key}:{key}"),
        "position": position(x, y, width, height, 3000 + x + y),
        "visual": {
            "visualType": "tableEx",
            "query": query,
            "objects": {
                "columnHeaders": [
                    {
                        "properties": {
                            "autoSizeColumnWidth": literal(True),
                            "columnAdjustment": literal("growToFit"),
                            "fontColor": solid(CARD_BACKGROUND),
                            "backColor": solid(NAVY),
                            "bold": literal(True),
                        }
                    }
                ],
                "values": [
                    {
                        "properties": {
                            "backColorPrimary": solid(CARD_BACKGROUND),
                            "backColorSecondary": solid(PAGE_BACKGROUND),
                            "fontColorPrimary": solid(NAVY),
                            "fontColorSecondary": solid(NAVY),
                        }
                    }
                ],
            },
            "visualContainerObjects": vco,
        },
    }


def page_json(page_name: str, display_name: str) -> dict[str, Any]:
    return {
        "$schema": PAGE_SCHEMA,
        "name": page_name,
        "displayName": display_name,
        "displayOption": "FitToPage",
        "height": 720,
        "width": 1280,
        "objects": {
            "background": [
                {
                    "properties": {
                        "color": solid(PAGE_BACKGROUND),
                        "transparency": literal(0),
                    }
                }
            ],
            "outspace": [
                {
                    "properties": {
                        "color": solid(NAVY),
                        "transparency": literal(0),
                    }
                }
            ],
        },
    }


def tables() -> tuple[Table, ...]:
    return (
        Table(
            "Date",
            "analytics_warehouse",
            "dim_date",
            (
                Column("date_key", "int64", hidden=True, format_string="0"),
                Column("date", "dateTime", source="date_day", format_string="dd/MM/yyyy"),
                Column("year", "int64", source="year_number", format_string="0"),
                Column("quarter", "int64", source="quarter_number", format_string="0"),
                Column("month_number", "int64", hidden=True, format_string="0"),
                Column("month", "string", source="month_name"),
                Column("month_start_date", "dateTime", format_string="MM/yyyy"),
                Column("week", "int64", source="week_number", format_string="0"),
                Column("day", "int64", source="day_of_month", format_string="0"),
                Column("is_weekend", "boolean"),
            ),
        ),
        Table(
            "Site",
            "analytics_warehouse",
            "dim_site",
            (
                Column("site_id", "string", hidden=True),
                Column("site_code", "string"),
                Column("site_name", "string"),
                Column("location_type", "string"),
                Column("is_active", "boolean"),
            ),
        ),
        Table(
            "Daily Work Orders",
            "analytics_marts",
            "daily_site_work_orders",
            (
                Column("site_id", "string", hidden=True),
                Column("created_date", "dateTime", hidden=True, format_string="dd/MM/yyyy"),
                Column("total_work_orders", "int64", hidden=True, format_string="#,0"),
                Column("completed_work_orders", "int64", hidden=True, format_string="#,0"),
                Column("critical_work_orders", "int64", hidden=True, format_string="#,0"),
                Column("unassigned_work_orders", "int64", hidden=True, format_string="#,0"),
                Column("total_repair_hours", "double", hidden=True, format_string="0.00"),
                Column("repair_duration_work_orders", "int64", hidden=True, format_string="#,0"),
            ),
            (
                Measure("Total Work Orders", "SUM('Daily Work Orders'[total_work_orders])", "#,0", "Tổng work order trong phạm vi lọc."),
                Measure("Completed Work Orders", "SUM('Daily Work Orders'[completed_work_orders])", "#,0", "Tổng work order completed hoặc verified."),
                Measure("Completion Rate", "DIVIDE([Completed Work Orders], [Total Work Orders])", "0.0%", "Tỷ lệ work order đã hoàn thành."),
                Measure("Critical Work Orders", "SUM('Daily Work Orders'[critical_work_orders])", "#,0", "Tổng work order priority critical."),
                Measure("Unassigned Work Orders", "SUM('Daily Work Orders'[unassigned_work_orders])", "#,0", "Tổng work order chưa phân công."),
                Measure("Average Repair Hours", "DIVIDE(SUM('Daily Work Orders'[total_repair_hours]), SUM('Daily Work Orders'[repair_duration_work_orders]))", "0.00", "Số giờ sửa chữa trung bình trên work order có duration."),
            ),
        ),
        Table(
            "Site Reliability",
            "analytics_marts",
            "site_reliability",
            (
                Column("site_id", "string", hidden=True),
                Column("work_order_count", "int64", hidden=True, format_string="#,0"),
                Column("completed_work_order_count", "int64", hidden=True, format_string="#,0"),
                Column("cancelled_work_order_count", "int64", hidden=True, format_string="#,0"),
                Column("average_repair_hours", "double", hidden=True, format_string="0.00"),
                Column("status_event_count", "int64", hidden=True, format_string="#,0"),
                Column("observed_status_seconds", "int64", hidden=True, format_string="#,0"),
                Column("on_hold_seconds", "int64", hidden=True, format_string="#,0"),
            ),
            (
                Measure("Reliability Work Orders", "SUM('Site Reliability'[work_order_count])", "#,0", "Tổng work order trong mart reliability."),
                Measure("Site Completed Work Orders", "SUM('Site Reliability'[completed_work_order_count])", "#,0", "Tổng work order hoàn thành trong mart reliability."),
                Measure("Site Completion Rate", "DIVIDE([Site Completed Work Orders], [Reliability Work Orders])", "0.0%", "Tỷ lệ hoàn thành tại các site được lọc."),
                Measure("Site Average Repair Hours", "AVERAGE('Site Reliability'[average_repair_hours])", "0.00", "Trung bình repair hours giữa các site có dữ liệu."),
                Measure("On-Hold Hours", "DIVIDE(SUM('Site Reliability'[on_hold_seconds]), 3600)", "#,0.0", "Tổng thời gian on-hold quy đổi sang giờ."),
            ),
        ),
        Table(
            "Ticket SLA",
            "analytics_marts",
            "ticket_sla",
            (
                Column("site_id", "string", hidden=True),
                Column("priority", "string"),
                Column("ticket_count", "int64", hidden=True, format_string="#,0"),
                Column("unresolved_ticket_count", "int64", hidden=True, format_string="#,0"),
                Column("first_response_met_count", "int64", hidden=True, format_string="#,0"),
                Column("resolution_breach_count", "int64", hidden=True, format_string="#,0"),
                Column("escalated_ticket_count", "int64", hidden=True, format_string="#,0"),
            ),
            (
                Measure("Tickets", "SUM('Ticket SLA'[ticket_count])", "#,0", "Tổng ticket."),
                Measure("Unresolved Tickets", "SUM('Ticket SLA'[unresolved_ticket_count])", "#,0", "Tổng ticket chưa resolved."),
                Measure("SLA Breaches", "SUM('Ticket SLA'[resolution_breach_count])", "#,0", "Tổng ticket breach resolution SLA."),
                Measure("SLA Breach Rate", "DIVIDE([SLA Breaches], [Tickets])", "0.0%", "Tỷ lệ breach resolution SLA."),
                Measure("Escalated Tickets", "SUM('Ticket SLA'[escalated_ticket_count])", "#,0", "Tổng ticket đã escalation."),
                Measure("First Response Met Rate", "DIVIDE(SUM('Ticket SLA'[first_response_met_count]), [Tickets])", "0.0%", "Tỷ lệ đáp ứng first-response SLA."),
            ),
        ),
        Table(
            "Inventory Consumption",
            "analytics_marts",
            "inventory_consumption",
            (
                Column("part_id", "string", hidden=True),
                Column("site_id", "string", hidden=True),
                Column("part_number", "string"),
                Column("part_name", "string"),
                Column("issue_movement_count", "int64", hidden=True, format_string="#,0"),
                Column("issued_quantity", "double", hidden=True, format_string="#,0.00"),
                Column("returned_quantity", "double", hidden=True, format_string="#,0.00"),
                Column("net_consumed_quantity", "double", hidden=True, format_string="#,0.00"),
            ),
            (
                Measure("Issued Quantity", "SUM('Inventory Consumption'[issued_quantity])", "#,0.00", "Tổng số lượng đã issue."),
                Measure("Returned Quantity", "SUM('Inventory Consumption'[returned_quantity])", "#,0.00", "Tổng số lượng đã return."),
                Measure("Net Consumed Quantity", "SUM('Inventory Consumption'[net_consumed_quantity])", "#,0.00", "Số lượng issue trừ return."),
            ),
        ),
        Table(
            "Technician Workload",
            None,
            None,
            (
                Column("technician_id", "string", hidden=True),
                Column("site_id", "string", hidden=True),
                Column("employee_code", "string"),
                Column("display_name", "string"),
                Column("role", "string"),
                Column("is_active", "boolean"),
                Column("assigned_work_orders", "int64", hidden=True, format_string="#,0"),
                Column("completed_work_orders", "int64", hidden=True, format_string="#,0"),
                Column("in_progress_work_orders", "int64", hidden=True, format_string="#,0"),
                Column("on_hold_work_orders", "int64", hidden=True, format_string="#,0"),
            ),
            (
                Measure("Assigned Technician Work Orders", "SUM('Technician Workload'[assigned_work_orders])", "#,0", "Tổng work order đã gán cho technician."),
                Measure("Completed Technician Work Orders", "SUM('Technician Workload'[completed_work_orders])", "#,0", "Tổng work order completed hoặc verified theo technician."),
                Measure("In-Progress Technician Work Orders", "SUM('Technician Workload'[in_progress_work_orders])", "#,0", "Tổng work order đang in progress theo technician."),
                Measure("On-Hold Technician Work Orders", "SUM('Technician Workload'[on_hold_work_orders])", "#,0", "Tổng work order on-hold theo technician."),
                Measure("Technician Completion Rate", "DIVIDE([Completed Technician Work Orders], [Assigned Technician Work Orders])", "0.0%", "Tỷ lệ completed trên assigned theo technician."),
            ),
            native_sql="""
select
    t.technician_id::text as technician_id,
    w.site_id::text as site_id,
    t.employee_code,
    t.display_name,
    t.role,
    t.is_active,
    count(w.work_order_id)::bigint as assigned_work_orders,
    count(w.work_order_id) filter (
        where w.status in ('completed', 'verified')
    )::bigint as completed_work_orders,
    count(w.work_order_id) filter (
        where w.status = 'in_progress'
    )::bigint as in_progress_work_orders,
    count(w.work_order_id) filter (
        where w.status = 'on_hold'
    )::bigint as on_hold_work_orders
from analytics_warehouse.dim_technician as t
left join analytics_warehouse.fact_work_order as w
    on w.assigned_technician_id = t.technician_id
where t.technician_id <> '00000000-0000-0000-0000-000000000000'::uuid
group by
    t.technician_id,
    w.site_id,
    t.employee_code,
    t.display_name,
    t.role,
    t.is_active
""".strip(),
        ),
    )


def table_tmdl(table: Table, server: str, database: str) -> str:
    lines = [f"table {tmdl_name(table.name)}", f"\tlineageTag: {stable_uuid(f'table:{table.name}')}", ""]
    for column in table.columns:
        lines.extend(
            [
                f"\tcolumn {tmdl_name(column.name)}",
                f"\t\tdataType: {column.data_type}",
            ]
        )
        if column.hidden:
            lines.append("\t\tisHidden")
        if column.format_string:
            lines.append(f"\t\tformatString: {column.format_string}")
        lines.extend(
            [
                f"\t\tlineageTag: {stable_uuid(f'column:{table.name}:{column.name}')}",
                "\t\tsummarizeBy: none",
                f"\t\tsourceColumn: {column.source or column.name}",
                "",
                "\t\tannotation SummarizationSetBy = Automatic",
                "",
            ]
        )
    for measure in table.measures:
        lines.extend(
            [
                f"\tmeasure {tmdl_name(measure.name)} = {measure.expression}",
                f"\t\tformatString: {measure.format_string}",
                f"\t\tdescription: {measure.description}",
                f"\t\tlineageTag: {stable_uuid(f'measure:{table.name}:{measure.name}')}",
                "",
            ]
        )

    lines.extend(
        [
            f"\tpartition {tmdl_name(table.name)} = m",
            "\t\tmode: import",
            "\t\tsource =",
            "\t\t\tlet",
            f'\t\t\t\tSource = PostgreSQL.Database("{m_text(server)}", "{m_text(database)}", [CreateNavigationProperties=false]),',
        ]
    )
    if table.native_sql:
        sql_lines = table.native_sql.splitlines()
        lines.append("\t\t\t\tSql = Text.Combine({")
        for index, sql_line in enumerate(sql_lines):
            comma = "," if index < len(sql_lines) - 1 else ""
            lines.append(f'\t\t\t\t\t"{m_text(sql_line)}"{comma}')
        lines.extend(
            [
                '\t\t\t\t}, "#(lf)"),',
                "\t\t\t\tData = Value.NativeQuery(Source, Sql, null, [EnableFolding=true])",
                "\t\t\tin",
                "\t\t\t\tData",
            ]
        )
    else:
        selected = ", ".join(
            f'"{m_text(column.source or column.name)}"' for column in table.columns
        )
        lines.extend(
            [
                f'\t\t\t\tData = Source{{[Schema="{table.schema}", Item="{table.source_name}"]}}[Data],',
                f"\t\t\t\tSelectedColumns = Table.SelectColumns(Data, {{{selected}}})",
                "\t\t\tin",
                "\t\t\t\tSelectedColumns",
            ]
        )
    lines.extend(
        [
            "",
            "\tannotation PBI_NavigationStepName = Navigation",
            "",
            "\tannotation PBI_ResultType = Table",
            "",
        ]
    )
    return "\n".join(lines)


def semantic_files(server: str, database: str) -> dict[Path, str]:
    model_tables = tables()
    base = Path(f"{PROJECT_NAME}.SemanticModel")
    files: dict[Path, str] = {
        base / ".platform": json_text(
            {
                "$schema": PLATFORM_SCHEMA,
                "metadata": {
                    "type": "SemanticModel",
                    "displayName": "Maintenance Analytics Model",
                    "description": "Batch analytics semantic model for maintenance reporting.",
                },
                "config": {
                    "version": "2.0",
                    "logicalId": stable_uuid("platform:semantic-model"),
                },
            }
        ),
        base / "definition.pbism": json_text(
            {
                "$schema": PBISM_SCHEMA,
                "version": "4.2",
                "settings": {},
            }
        ),
        base / "definition" / "database.tmdl": (
            "database\n"
            "\tcompatibilityLevel: 1601\n\n"
            f"\tannotation PBI_QueryOrder = [{','.join(json.dumps(t.name) for t in model_tables)}]\n"
        ),
        base / "definition" / "model.tmdl": (
            "model Model\n"
            "\tculture: en-US\n"
            "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
            "\tsourceQueryCulture: en-US\n"
            "\tdataAccessOptions\n"
            "\t\tlegacyRedirects\n"
            "\t\treturnErrorValuesAsNull\n\n"
            + "\n".join(f"ref table {tmdl_name(table.name)}" for table in model_tables)
            + "\n\nref cultureInfo en-US\n"
        ),
        base / "definition" / "cultures" / "en-US.tmdl": (
            "cultureInfo en-US\n\n"
            "\tlinguisticMetadata =\n"
            "\t\t{\"Version\":\"1.0.0\",\"Language\":\"en-US\"}\n"
            "\tcontentType: json\n"
        ),
    }
    relationships = [
        ("Daily Work Orders", "created_date", "Date", "date"),
        ("Daily Work Orders", "site_id", "Site", "site_id"),
        ("Site Reliability", "site_id", "Site", "site_id"),
        ("Ticket SLA", "site_id", "Site", "site_id"),
        ("Inventory Consumption", "site_id", "Site", "site_id"),
        ("Technician Workload", "site_id", "Site", "site_id"),
    ]
    relationship_lines: list[str] = []
    for from_table, from_column, to_table, to_column in relationships:
        label = f"relationship:{from_table}:{from_column}:{to_table}:{to_column}"
        relationship_lines.extend(
            [
                f"relationship {stable_uuid(label)}",
                f"\tfromColumn: {tmdl_name(from_table)}.{tmdl_name(from_column)}",
                f"\ttoColumn: {tmdl_name(to_table)}.{tmdl_name(to_column)}",
                "",
            ]
        )
    files[base / "definition" / "relationships.tmdl"] = "\n".join(relationship_lines)
    for table in model_tables:
        files[base / "definition" / "tables" / f"{table.name}.tmdl"] = table_tmdl(
            table, server, database
        )
    return files


def report_pages() -> list[tuple[str, str, list[dict[str, Any]]]]:
    pages: list[tuple[str, str, list[dict[str, Any]]]] = []

    key = "overview"
    visuals = title_visual(
        key,
        "Tổng quan điều hành",
        "Work order theo batch analytics đã được dbt kiểm thử",
    )
    visuals.extend(
        [
            slicer_visual(key, "site", "Site", "site_name", "Site", 808, 200),
            slicer_visual(key, "date", "Date", "date", "Khoảng ngày", 1016, 240, mode="Between"),
        ]
    )
    cards = [
        ("total", "Total Work Orders", "Tổng work order", BLUE),
        ("completed", "Completed Work Orders", "Đã hoàn thành", GREEN),
        ("rate", "Completion Rate", "Tỷ lệ hoàn thành", TEAL),
        ("critical", "Critical Work Orders", "Mức critical", RED),
        ("unassigned", "Unassigned Work Orders", "Chưa phân công", AMBER),
    ]
    for index, (card_key, measure, label, color) in enumerate(cards):
        visuals.append(
            card_visual(
                key,
                card_key,
                "Daily Work Orders",
                measure,
                label,
                24 + index * 248,
                color,
            )
        )
    visuals.extend(
        [
            chart_visual(
                key,
                "monthly-trend",
                "lineChart",
                "Xu hướng work order theo tháng",
                ("Date", "month_start_date", "Tháng"),
                [
                    ("Daily Work Orders", "Total Work Orders", "Tổng work order", BLUE),
                    ("Daily Work Orders", "Completed Work Orders", "Đã hoàn thành", GREEN),
                ],
                (24, 232, 760, 464),
                sort_measure=("Daily Work Orders", "Total Work Orders"),
                sort_direction="Ascending",
            ),
            chart_visual(
                key,
                "site-volume",
                "clusteredBarChart",
                "Khối lượng theo site",
                ("Site", "site_name", "Site"),
                [
                    ("Daily Work Orders", "Total Work Orders", "Tổng work order", BLUE),
                    ("Daily Work Orders", "Completed Work Orders", "Đã hoàn thành", GREEN),
                ],
                (800, 232, 456, 464),
                sort_measure=("Daily Work Orders", "Total Work Orders"),
            ),
        ]
    )
    pages.append((stable_hex("page:overview"), "Tổng quan điều hành", visuals))

    key = "reliability"
    visuals = title_visual(
        key,
        "Độ tin cậy & khối lượng công việc",
        "Site reliability và workload kỹ thuật viên",
    )
    visuals.append(slicer_visual(key, "site", "Site", "site_name", "Site", 1016, 240))
    reliability_cards = [
        ("work-orders", "Reliability Work Orders", "Work order", BLUE),
        ("completion-rate", "Site Completion Rate", "Tỷ lệ hoàn thành", GREEN),
        ("repair-hours", "Site Average Repair Hours", "Giờ sửa chữa TB", TEAL),
        ("on-hold-hours", "On-Hold Hours", "Giờ on-hold", AMBER),
    ]
    for index, (card_key, measure, label, color) in enumerate(reliability_cards):
        visuals.append(
            card_visual(
                key,
                card_key,
                "Site Reliability",
                measure,
                label,
                24 + index * 310,
                color,
                width=302,
            )
        )
    visuals.extend(
        [
            chart_visual(
                key,
                "completion-by-site",
                "clusteredBarChart",
                "Tỷ lệ hoàn thành theo site",
                ("Site", "site_name", "Site"),
                [("Site Reliability", "Site Completion Rate", "Tỷ lệ hoàn thành", GREEN)],
                (24, 232, 600, 220),
                sort_measure=("Site Reliability", "Site Completion Rate"),
            ),
            chart_visual(
                key,
                "repair-by-site",
                "clusteredColumnChart",
                "Thời gian sửa chữa trung bình theo site",
                ("Site", "site_name", "Site"),
                [("Site Reliability", "Site Average Repair Hours", "Giờ sửa chữa TB", TEAL)],
                (640, 232, 616, 220),
                sort_measure=("Site Reliability", "Site Average Repair Hours"),
            ),
            table_visual(
                key,
                "technician-table",
                "Workload kỹ thuật viên",
                [
                    ("Technician Workload", "employee_code", "Mã nhân viên", False),
                    ("Technician Workload", "display_name", "Kỹ thuật viên", False),
                    ("Technician Workload", "role", "Vai trò", False),
                    ("Technician Workload", "Assigned Technician Work Orders", "Được phân công", True),
                    ("Technician Workload", "Completed Technician Work Orders", "Đã hoàn thành", True),
                    ("Technician Workload", "In-Progress Technician Work Orders", "Đang thực hiện", True),
                    ("Technician Workload", "Technician Completion Rate", "Tỷ lệ hoàn thành", True),
                ],
                (24, 468, 1232, 228),
                sort_measure=("Technician Workload", "Assigned Technician Work Orders"),
            ),
        ]
    )
    pages.append((stable_hex("page:reliability"), "Độ tin cậy & khối lượng", visuals))

    key = "sla-inventory"
    visuals = title_visual(
        key,
        "SLA & phụ tùng",
        "Ticket SLA và stock movement gắn với work order",
    )
    visuals.append(slicer_visual(key, "site", "Site", "site_name", "Site", 1016, 240))
    sla_cards = [
        ("tickets", "Tickets", "Tổng ticket", BLUE),
        ("unresolved", "Unresolved Tickets", "Chưa resolved", AMBER),
        ("breach-rate", "SLA Breach Rate", "Tỷ lệ breach SLA", RED),
        ("escalated", "Escalated Tickets", "Đã escalation", PURPLE),
        ("first-response", "First Response Met Rate", "Đạt first response", GREEN),
    ]
    for index, (card_key, measure, label, color) in enumerate(sla_cards):
        visuals.append(
            card_visual(
                key,
                card_key,
                "Ticket SLA",
                measure,
                label,
                24 + index * 248,
                color,
            )
        )
    visuals.extend(
        [
            chart_visual(
                key,
                "sla-priority",
                "clusteredColumnChart",
                "Ticket và SLA breach theo priority",
                ("Ticket SLA", "priority", "Priority"),
                [
                    ("Ticket SLA", "Tickets", "Tổng ticket", BLUE),
                    ("Ticket SLA", "Unresolved Tickets", "Chưa resolved", AMBER),
                    ("Ticket SLA", "SLA Breaches", "Breach SLA", RED),
                ],
                (24, 232, 600, 220),
                sort_measure=("Ticket SLA", "Tickets"),
            ),
            chart_visual(
                key,
                "top-parts",
                "clusteredBarChart",
                "Phụ tùng tiêu thụ nhiều nhất",
                ("Inventory Consumption", "part_name", "Phụ tùng"),
                [("Inventory Consumption", "Net Consumed Quantity", "Net consumed", TEAL)],
                (640, 232, 616, 220),
                sort_measure=("Inventory Consumption", "Net Consumed Quantity"),
            ),
            table_visual(
                key,
                "parts-table",
                "Chi tiết luân chuyển phụ tùng",
                [
                    ("Inventory Consumption", "part_number", "Mã phụ tùng", False),
                    ("Inventory Consumption", "part_name", "Tên phụ tùng", False),
                    ("Inventory Consumption", "Issued Quantity", "Đã issue", True),
                    ("Inventory Consumption", "Returned Quantity", "Đã return", True),
                    ("Inventory Consumption", "Net Consumed Quantity", "Net consumed", True),
                ],
                (24, 468, 1232, 228),
                sort_measure=("Inventory Consumption", "Net Consumed Quantity"),
            ),
        ]
    )
    pages.append((stable_hex("page:sla-inventory"), "SLA & phụ tùng", visuals))
    return pages


def report_files() -> dict[Path, str]:
    report = Path(f"{PROJECT_NAME}.Report")
    pages = report_pages()
    files: dict[Path, str] = {
        Path(f"{PROJECT_NAME}.pbip"): json_text(
            {
                "$schema": PBIP_SCHEMA,
                "version": "1.0",
                "artifacts": [{"report": {"path": f"{PROJECT_NAME}.Report"}}],
                "settings": {"enableAutoRecovery": True},
            }
        ),
        report / ".platform": json_text(
            {
                "$schema": PLATFORM_SCHEMA,
                "metadata": {
                    "type": "Report",
                    "displayName": "Maintenance Analytics",
                    "description": "Báo cáo tổng hợp cho Data Platform bảo trì.",
                },
                "config": {
                    "version": "2.0",
                    "logicalId": stable_uuid("platform:report"),
                },
            }
        ),
        report / "definition.pbir": json_text(
            {
                "$schema": PBIR_SCHEMA,
                "version": "4.0",
                "datasetReference": {
                    "byPath": {"path": f"../{PROJECT_NAME}.SemanticModel"}
                },
            }
        ),
        report / "definition" / "version.json": json_text(
            {"$schema": VERSION_SCHEMA, "version": "2.0.0"}
        ),
        report / "definition" / "report.json": json_text(
            {
                "$schema": REPORT_SCHEMA,
                "themeCollection": {
                    "baseTheme": {
                        "name": "CY24SU10",
                        "reportVersionAtImport": {
                            "visual": "2.5.0",
                            "report": "3.0.0",
                            "page": "2.4.0",
                        },
                        "type": "SharedResources",
                    }
                },
            }
        ),
        report / "definition" / "pages" / "pages.json": json_text(
            {
                "$schema": PAGES_SCHEMA,
                "pageOrder": [page_name for page_name, _display, _visuals in pages],
                "activePageName": pages[0][0],
            }
        ),
    }
    for page_name, display_name, visuals in pages:
        page_base = report / "definition" / "pages" / page_name
        files[page_base / "page.json"] = json_text(page_json(page_name, display_name))
        for visual in visuals:
            visual_name = visual["name"]
            files[page_base / "visuals" / visual_name / "visual.json"] = json_text(visual)
    return files


def generated_files(server: str, database: str) -> dict[Path, str]:
    files = report_files()
    files.update(semantic_files(server, database))
    return files


def write_files(files: dict[Path, str]) -> None:
    for relative_path, content in sorted(files.items(), key=lambda item: str(item[0])):
        path = OUTPUT_ROOT / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def check_files(files: dict[Path, str]) -> list[str]:
    problems: list[str] = []
    for relative_path, expected in sorted(files.items(), key=lambda item: str(item[0])):
        path = OUTPUT_ROOT / relative_path
        if not path.exists():
            problems.append(f"missing: {relative_path}")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            problems.append(f"changed: {relative_path}")
    return problems


def validate_location(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise argparse.ArgumentTypeError(f"{label} must not be empty")
    if any(character in value for character in ("\n", "\r", "\x00")):
        raise argparse.ArgumentTypeError(f"{label} contains an invalid character")
    return value


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--server",
        default=DEFAULT_SERVER,
        type=lambda value: validate_location(value, "server"),
        help=f"PostgreSQL server[:port] (default: {DEFAULT_SERVER})",
    )
    parser.add_argument(
        "--database",
        default=DEFAULT_DATABASE,
        type=lambda value: validate_location(value, "database"),
        help=f"PostgreSQL database (default: {DEFAULT_DATABASE})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify generated output matches the deterministic generator.",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    files = generated_files(args.server, args.database)
    if args.check:
        problems = check_files(files)
        if problems:
            print("Power BI project is not up to date:", file=sys.stderr)
            for problem in problems:
                print(f"- {problem}", file=sys.stderr)
            return 1
        print(f"Power BI project is up to date ({len(files)} generated files).")
        return 0
    write_files(files)
    print(f"Generated {len(files)} files under {OUTPUT_ROOT}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
