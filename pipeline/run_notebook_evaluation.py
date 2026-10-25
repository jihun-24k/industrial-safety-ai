"""Execute the existing notebook's core evaluation cells with explicit live flags."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

from pipeline import pdf_pipeline as pp


def execute(*, live=False, build_index=False, env_file=None, timeout=1200):
    import nbformat
    from nbclient import NotebookClient
    from dotenv import load_dotenv

    if build_index and not live:
        raise ValueError('--build-index requires --live')
    cfg = pp.config_at(pp.ROOT / 'pipeline/config.json')
    env_file = Path(env_file or pp.ROOT / '.env').resolve()
    load_dotenv(env_file, override=False)
    if live and not os.getenv('OPENAI_API_KEY'):
        raise ValueError('OPENAI_API_KEY missing in environment or the selected .env file')
    os.environ['LANGSMITH_TRACING'] = 'false'
    os.environ.pop('LANGCHAIN_TRACING_V2', None)
    os.environ['SAFEOPS_ENV_FILE'] = str(env_file)
    os.environ['SAFEOPS_RUN_LIVE'] = '1' if live else '0'
    os.environ['SAFEOPS_RUN_RAGAS'] = '1' if live else '0'
    os.environ['PATH'] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')
    if not (cfg['output_root'] / 'prepared.json').exists():
        pp.prepare(cfg)
    if build_index:
        pp.build(cfg, pp.embeddings(cfg, env_file))
    if live and not (cfg['output_root'] / 'current.json').exists():
        raise ValueError('No active index. Use --live --build-index for the initial embedding build.')

    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    output = cfg['output_root'] / 'evaluation' / 'notebooks' / run_id
    output.mkdir(parents=True)
    os.environ['IPYTHONDIR'] = str(output / 'ipython')
    os.environ['JUPYTER_RUNTIME_DIR'] = str(output / 'runtime')
    source = pp.ROOT / 'notebooks/safepath_question_validation.ipynb'
    notebook = nbformat.read(source, as_version=4)
    # Sections 00–07 evaluate the current versioned question set.
    # Later appendices contain independent tuning/vision experiments and old artifacts.
    appendix_start = next((i for i, cell in enumerate(notebook.cells)
                           if cell.cell_type == 'markdown'
                           and cell.source.startswith('## 08.')), len(notebook.cells))
    notebook.cells = notebook.cells[:appendix_start]
    for cell in notebook.cells:
        if cell.cell_type == 'code':
            cell.outputs = []
            cell.execution_count = None
    result_file = output / 'safepath_question_validation.executed.ipynb'
    status = {'source_notebook': str(source), 'executed_notebook': str(result_file),
              'live': live, 'build_index': build_index, 'sections': '00–07',
              'external_api_enabled': live, 'langsmith_upload': False, 'status': 'running'}
    pp.write_json(output / 'execution.json', status)

    def on_cell_complete(cell, cell_index, **_):
        if cell.cell_type == 'code':
            print(f'Notebook cell {cell_index} executed', flush=True)

    client = NotebookClient(notebook, timeout=timeout, kernel_name='python3',
                            resources={'metadata': {'path': str(pp.ROOT)}},
                            on_cell_executed=on_cell_complete)
    try:
        client.execute()
        status['status'] = 'completed' if live else 'offline_preview_completed'
    except Exception as exc:
        status['status'] = 'failed'
        status['error_type'] = type(exc).__name__
        raise RuntimeError(f'Notebook execution failed ({type(exc).__name__}); inspect {result_file}') from None
    finally:
        nbformat.write(notebook, result_file)
        pp.write_json(output / 'execution.json', status)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--live', action='store_true', help='Generate answers and run RAGAS through OpenAI')
    mode.add_argument('--offline', action='store_false', dest='live', help='Execute with all external calls disabled (default)')
    parser.set_defaults(live=False)
    parser.add_argument('--build-index', action='store_true', help='Build FAISS first; embeds uncached document text')
    parser.add_argument('--env-file')
    args = parser.parse_args()
    print(json.dumps(execute(live=args.live, build_index=args.build_index, env_file=args.env_file),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
