""" Utility functions for files """
import segyio
import numpy as np
import pandas as pd
from tqdm import tqdm
import glob

from ..batchflow import FilesIndex
from .seismic_index import SegyFilesIndex

def write_segy_file(data, df, samples, path, sorting=None, segy_format=1):
    """Write data and headers into SEGY file.

    Parameters
    ----------
    data : array-like
        Array of traces.
    df : DataFrame
        DataFrame with trace headers data.
    samples : array, same length as traces
        Time samples for trace data.
    path : str
        Path to output file.
    sorting : int
        SEGY file sorting.
    format : int
        SEGY file format.

    Returns
    -------
    """
    spec = segyio.spec()
    spec.sorting = sorting
    spec.format = segy_format
    spec.samples = samples
    spec.tracecount = len(data)

    df.columns = [getattr(segyio.TraceField, k) for k in df.columns]
    df[getattr(segyio.TraceField, 'TRACE_SEQUENCE_FILE')] = np.arange(len(df)) + 1

    with segyio.create(path, spec) as file:
        file.trace = data
        meta = df.to_dict('index')
        for i, x in enumerate(file.header[:]):
            x.update(meta[i])

def merge_segy_files(paths, output_path, bar=True):
    """Merge segy files into a single segy file.

    Parameters
    ----------
    paths : str or list of str
        Paths of files to merge, can use glob patterns
    output_path : str
        Path to output file.
    bar : bool
        Whether to how progress bar (default = True).

    """
    if isinstance(paths, str):
        paths = [paths]

    if len(paths) == 0:
        raise ValueError("`paths` cannot be empty.")

    files_list = [f for path in paths for f in glob.iglob(path, recursive=True)]

    tracecounts = 0
    samples = None

    for fname in files_list:
        with segyio.open(fname, strict=False) as f:
            if samples is None:
                samples = f.samples
            else:
                if np.all(samples != f.samples):
                    raise ValueError("Inconsistent samples in files!" +
                                     f"Samples is {f.samples} in {fname}, previous value was {samples}")
            tracecounts += f.tracecount

    spec = segyio.spec()
    spec.sorting = None
    spec.format = 1
    spec.tracecount = tracecounts
    spec.samples = samples

    with segyio.create(output_path, spec) as dst:
        i = 0
        iterable = tqdm(files_list) if bar else files_list
        for index in iterable:
            with segyio.open(index, strict=False) as src:
                dst.trace[i: i + src.tracecount] = src.trace
                dst.header[i: i + src.tracecount] = src.header
                for j in range(src.tracecount):
                    dst.header[i + j].update({segyio.TraceField.TRACE_SEQUENCE_FILE: i + j + 1})

            i += src.tracecount


def merge_picking_files(output_path, **kwargs):
    """Merge picking files into a single file.

    Parameters
    ----------
    output_path : str
        Path to output file.
    kwargs : dict
        Keyword arguments to index input files.

    Returns
    -------
    """
    files_index = FilesIndex(**kwargs)
    dfs = []
    for i in files_index.indices:
        path = files_index.get_fullpath(i)
        dfs.append(pd.read_csv(path))

    df = pd.concat(dfs, ignore_index=True)
    df.to_csv(output_path, index=False)
