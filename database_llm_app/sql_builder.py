from __future__ import annotations

from .models import StructuredQuery
from .schema_graph import SchemaGraph
from .semantic_dictionary import SemanticDictionary


class SQLBuilder:
    def __init__(self, *, dictionary: SemanticDictionary, schema_graph: SchemaGraph, row_limit: int):
        self._dictionary = dictionary
        self._schema_graph = schema_graph
        self._row_limit = row_limit

    def build(self, query: StructuredQuery) -> str:
        query.limit = max(1, min(query.limit, self._row_limit))
        if query.intent == "aggregate":
            return self._build_aggregate(query)
        if query.intent == "trend":
            return self._build_trend(query)
        if query.intent == "ranking":
            return self._build_ranking(query)
        return self._build_lookup(query)

    def _build_ranking(self, query: StructuredQuery) -> str:
        metric = self._dictionary.payload["metrics"][query.metric]
        dimensions = query.dimensions or ["fund"]
        select_parts, group_parts, joins = self._dimension_parts(dimensions)
        select_clause = ",\n  ".join(select_parts + [f"{metric['expression']} AS metric_value"])
        group_clause = ",\n  ".join(group_parts)
        where_clause = self._where_clause(query)
        return f"""SELECT TOP {query.limit}
  {select_clause}
FROM {self._schema_graph.payload['base_table']}
{joins}
{where_clause}
GROUP BY
  {group_clause}
ORDER BY metric_value {query.sort_direction.upper()}"""

    def _build_aggregate(self, query: StructuredQuery) -> str:
        metric = self._dictionary.payload["metrics"][query.metric]
        where_clause = self._where_clause(query)
        return f"""SELECT
  {metric['expression']} AS metric_value
FROM {self._schema_graph.payload['base_table']}
{where_clause}"""

    def _build_trend(self, query: StructuredQuery) -> str:
        metric = self._dictionary.payload["metrics"][query.metric]
        dimensions = [item for item in query.dimensions if item != "proc_date"]
        select_parts = ["t.PROC_DATE AS proc_date"]
        group_parts = ["t.PROC_DATE"]
        joins = ""
        if dimensions:
            extra_select, extra_group, joins = self._dimension_parts(dimensions)
            select_parts.extend(extra_select)
            group_parts.extend(extra_group)
        select_parts.append(f"{metric['expression']} AS metric_value")
        where_clause = self._where_clause(query, allow_latest=False)
        return f"""SELECT TOP {query.limit}
  {", ".join(select_parts)}
FROM {self._schema_graph.payload['base_table']}
{joins}
{where_clause}
GROUP BY
  {", ".join(group_parts)}
ORDER BY t.PROC_DATE DESC"""

    def _build_lookup(self, query: StructuredQuery) -> str:
        joins = self._joins_for({"fund", "broker", "item"})
        where_clause = self._where_clause(query)
        return f"""SELECT TOP {query.limit}
  t.PROC_DATE,
  t.FUND_CODE,
  f.FUND_NAME,
  t.TRPL_CODE,
  p.TRPL_NAME,
  t.ITMS_CODE,
  i.ITMS_NAME,
  t.TRNS_AMT,
  t.CNTC_QNTY,
  t.BUYN_SLNG_DNCD
FROM {self._schema_graph.payload['base_table']}
{joins}
{where_clause}
ORDER BY {self._schema_graph.payload['default_order_expression']}"""

    def _dimension_parts(self, dimensions: list[str]) -> tuple[list[str], list[str], str]:
        select_parts: list[str] = []
        group_parts: list[str] = []
        required_joins: set[str] = set()
        for name in dimensions:
            definition = self._dictionary.payload["dimensions"][name]
            select_parts.append(f"{definition['code_expression']} AS {name}_code")
            group_parts.append(definition["code_expression"])
            if definition["label_expression"]:
                select_parts.append(f"{definition['label_expression']} AS {name}_label")
                group_parts.append(definition["label_expression"])
            if definition["requires_join"]:
                required_joins.add(definition["requires_join"])
        return select_parts, group_parts, self._joins_for(required_joins)

    def _joins_for(self, required_joins: set[str]) -> str:
        lines = [self._schema_graph.payload["joins"][name] for name in sorted(required_joins)]
        return "\n".join(lines)

    def _where_clause(self, query: StructuredQuery, *, allow_latest: bool = True) -> str:
        filters = query.filters
        conditions: list[str] = []
        if filters.fund_code:
            conditions.append(f"t.FUND_CODE = '{filters.fund_code}'")
        if filters.broker_code:
            conditions.append(f"t.TRPL_CODE = '{filters.broker_code}'")
        if filters.item_code:
            conditions.append(f"t.ITMS_CODE = '{filters.item_code}'")
        if filters.buy_sell in {"B", "S"}:
            conditions.append(f"t.BUYN_SLNG_DNCD = '{filters.buy_sell}'")
        if filters.proc_date.type == "exact" and filters.proc_date.value:
            conditions.append(f"t.PROC_DATE = '{filters.proc_date.value}'")
        elif filters.proc_date.type == "recent" and filters.proc_date.recent_days:
            conditions.append(
                f"TRY_CONVERT(date, t.PROC_DATE) >= DATEADD(day, -{int(filters.proc_date.recent_days)}, CAST(GETDATE() AS date))"
            )
        elif allow_latest and filters.proc_date.type == "latest":
            conditions.append("t.PROC_DATE = (SELECT MAX(PROC_DATE) FROM dbo.PFO_FTOP_INTG_TR)")
        if not conditions:
            return ""
        return "WHERE " + "\n  AND ".join(conditions)
