"""Shared graph/vector evidence assembly for serving and evaluation."""
from collections import defaultdict


def evidence_rows(retrieval):
    """Union by source chunk ID, retaining graph provenance on vector duplicates."""
    if 'context_results' in retrieval:
        return retrieval['context_results']
    rows = {}
    for name in ('results', 'linked_results', 'graph_results'):
        for row in retrieval.get(name, []):
            key = row['chunk_id']
            if key in rows:
                rows[key].update({k: v for k, v in row.items() if k.startswith('graph_')})
            else:
                rows[key] = dict(row)
    return list(rows.values())


def path_text(row):
    paths = row.get('graph_paths', [])
    if not paths:
        return ''
    # Shortest path is enough for the prompt; full paths remain in the API metadata.
    path = min(paths, key=lambda p: p['hops'])
    labels = [label.replace('\n', ' ') for label in path['labels']]
    parts = [labels[0]]
    for relation, label in zip(path['relations'], labels[1:]):
        parts.append(f' —[{relation}]→ {label}')
    details = ' / '.join(path.get('conditions', []) + path.get('statuses', []))
    return '[그래프 경로: ' + ''.join(parts) + (f'; 조건·상태: {details}' if details else '') + ']'


def select_context_rows(vector_rows, graph_rows, *, max_docs=20, max_chars=24000, priority_rows=()):
    """Round-robin evidence categories so contacts/reporting survive multi-query volume."""
    union = {r['chunk_id']: r for r in evidence_rows({'results': vector_rows, 'graph_results': graph_rows})}
    groups = defaultdict(list)
    for row in graph_rows:
        groups[row.get('graph_group', 'guidance')].append(union[row['chunk_id']])
    groups['vector'] = [union[r['chunk_id']] for r in vector_rows]
    selected, seen, size = [], set(), 0
    for row in priority_rows:
        cost = len(row['text']) + len(path_text(row)) + 300
        if row['chunk_id'] not in seen and len(selected) < max_docs and size + cost <= max_chars:
            selected.append(row)
            seen.add(row['chunk_id'])
            size += cost
    while any(groups.values()) and len(selected) < max_docs:
        for name in ('material', 'guidance', 'procedure', 'contact', 'hazard', 'web', 'vector'):
            while groups[name]:
                row = groups[name].pop(0)
                if row['chunk_id'] in seen:
                    continue
                seen.add(row['chunk_id'])
                cost = len(row['text']) + len(path_text(row)) + 300
                if size + cost <= max_chars:
                    selected.append(row)
                    size += cost
                    break
            if len(selected) >= max_docs:
                break
    return selected
