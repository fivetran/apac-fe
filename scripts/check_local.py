"""Offline YAML/Jinja/reference checks, NOT dbt Charts or Snowflake validation.
Run: python scripts/check_local.py
Dependencies: PyYAML and Jinja2 (normally available with dbt Charts).
"""
from pathlib import Path
import re
from collections.abc import Mapping
import yaml
from jinja2 import Environment, StrictUndefined, meta

ROOT = Path(__file__).resolve().parents[1]
class UniqueLoader(yaml.SafeLoader):
    pass

def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f'Duplicate YAML key: {key}')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result
UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)

def load(path):
    return yaml.load(path.read_text(), Loader=UniqueLoader)

def refs(sql):
    return set(re.findall(r'queries\.([A-Za-z_][A-Za-z_0-9]*)', sql))

def layout_refs(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for item in node:
            yield from layout_refs(item)
    elif isinstance(node, dict):
        for key in ('rows', 'cols', 'tabs', 'items', 'item'):
            if key in node:
                yield from layout_refs(node[key])

def mock_filter(column, value, operator='='):
    # This is for offline syntax checks only. Actual binding is done by dct.
    if value is None or value == '' or value == []:
        return '1=1'
    if operator != '=':
        raise ValueError(f'Unexpected operator in this starter: {operator}')
    escaped = str(value).replace("'", "''")
    return f"{column} = '{escaped}'"

class QueryMap(Mapping):
    def __init__(self, queries, values, env):
        self.queries, self.values, self.env = queries, values, env
        self.stack = []
        self.cache = {}
    def __iter__(self):
        return iter(self.queries)
    def __len__(self):
        return len(self.queries)
    def __getitem__(self, name):
        if name in self.stack:
            raise ValueError(f'Query reference cycle: {self.stack + [name]}')
        if name in self.cache:
            return self.cache[name]
        self.stack.append(name)
        rendered = self.env.from_string(self.queries[name]['sql']).render(
            **self.values, queries=self, filter=mock_filter)
        self.stack.pop()
        self.cache[name] = f'({rendered.strip()}) AS {name}'
        return self.cache[name]

def main():
    config = load(ROOT / 'dbt_charts.yml')
    for file in (ROOT / 'config_examples').glob('*.yml'):
        load(file)
    env = Environment(undefined=StrictUndefined)
    boards = list((ROOT / 'charts').glob('*.yml'))
    query_total = variant_total = 0
    for path in boards:
        b = load(path)
        assert b['source'] in config['sources'], (path, 'unknown source')
        q, charts, variables = b['queries'], b['charts'], b.get('variables', {})
        query_total += len(q)
        for name, definition in q.items():
            assert set(definition) == {'sql'}, (path, name, 'unexpected local query shape')
            template = env.parse(definition['sql'])
            missing = meta.find_undeclared_variables(template) - set(variables) - {'queries','filter'}
            assert not missing, (path, name, missing)
            assert refs(definition['sql']) <= set(q), (path, name, 'missing query reference')
            assert re.match(r'\s*(SELECT|WITH|\{%\s*if)', definition['sql'], re.I), (path, name)
        for name, c in charts.items():
            if c['type'] != 'callout':
                assert c['query'] in q, (path, name, 'missing chart query')
        for name in layout_refs({'rows':b['rows']}):
            assert name in charts, (path, name, 'missing layout chart')
        for name, v in variables.items():
            if 'query' in v:
                assert v['query'].startswith('queries.') and v['query'].split('.',1)[1] in q
        defaults = {k:v.get('default') for k,v in variables.items()}
        states = [defaults]
        if 'start_date' in variables:
            states += [defaults | {'start_date':'2026-09-01','end_date':'2026-09-07'},
                       defaults | {'end_date':'2026-09-07'},
                       defaults | {'start_date':'2026-09-01'},
                       defaults | {'start_date':'2026-10-01','end_date':'2026-01-01'},
                       defaults | {'start_date':'2026-01-01','end_date':'2026-10-22'}]
        if 'connection_id' in variables:
            states += [defaults | {'connection_id':"connection_with_quote_'_test"}]
        if 'event_id' in variables:
            states += [defaults | {'event_id':'event-123','event_scope':'All events'}]
        if 'usage_month' in variables:
            states += [defaults | {'usage_month':'2026-09-01','connection_id':'example-connection'}]
        if 'hours_before' in variables:
            states += [defaults | {'hours_before':0.25,'hours_after':1.0}, defaults | {'investigations':0}]
        for values in states:
            qm = QueryMap(q,values,env)
            for name in q:
                rendered = qm[name]
                assert '{{' not in rendered and '{%' not in rendered, (path,name)
                variant_total += 1
        print(f'PASS {path.name}: {len(q)} queries; {len(charts)} charts; {len(states)} input states')
    assert 20 * (1 - 0.25) == 15
    assert 20 * (1 - 0.25) * 150 == 2250
    assert 12 * (20 * (1 - 0.25) * 150 - 0) - 0 == 27000
    assert 12 * (2250 - 100) - 500 == 25300
    assert 20 * (0.25 - 1) * 150 == -2250
    print(f'PASS: {len(boards)} boards, {query_total} queries, {variant_total} offline template expansions.')
    print('NOT CHECKED: dct schema/renderer, parameter binding, live source data, privileges, Snowflake SQL execution.')

if __name__ == '__main__':
    main()
