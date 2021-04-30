""" Utils for QC metrics """

import re

import pandas as pd
import numpy as np

from matplotlib import pyplot as plt
from matplotlib import colors
import seaborn as sns

def parse_tuple(str_arg):
    """Parse str arg to tuple."""
    splitted = str_arg.split(',')
    if len(splitted) < 2:
        raise ValueError(f'Wrong input format: {str_arg}!')
    return tuple([int(val) for val in splitted])

def calc_range(arr):
    """Calculate minimal and maximal values for plotting.
    Calcutates 5th an 95th percentile of 3D array along (0,1) axes.
    If 5th percentile is above zero, returns small negative values instead.
    If 95th percentile is below zero, returns small positive values instead.
    """
    vmins = np.min((np.nanpercentile(arr, 5, axis=(0, 1)), [-1e-6]*arr.shape[-1]), axis=0)
    vmaxs = np.max((np.nanpercentile(arr, 95, axis=(0, 1)), [1e-6]*arr.shape[-1]), axis=0)
    return vmins, vmaxs

# pylint: disable=too-many-arguments
def plot_metrics(imgs, titles, vmins, vmaxs, cmaps, cols=2, xlabel='xlines', ylabel='ilines',
                 save_to=None, show_plot=False, title=None, **kwargs):
    """Plotter for QC metrics"""
    n = imgs.shape[-1]
    rows = n // cols + 1 if n % cols != 0 else n // cols

    if imgs.shape[0] > imgs.shape[1]:
        col_size, row_size, fraction, y_margin = 10, 10, 0.098, 0.95
    else:
        col_size, row_size, fraction, y_margin = 14, 9, 0.021, 0.91

    if isinstance(xlabel, str) and isinstance(ylabel, str):
        xlabel = [xlabel]*n
        ylabel = [ylabel]*n

    fig, ax = plt.subplots(rows, cols, figsize=(col_size*cols, row_size*rows))
    ax = np.atleast_2d(ax)
    for i in range(rows):
        for j in range(cols):
            n_axis = i*cols + j
            if n_axis < n:
                img_n = imgs[:, :, n_axis]
                default_kwargs = {'cmap': cmaps[n_axis]}
                divnorm = colors.TwoSlopeNorm(vmin=vmins[n_axis], vcenter=0, vmax=vmaxs[n_axis])
                img_ = ax[i][j].imshow(img_n, **{**default_kwargs, **kwargs}, norm=divnorm)

                ax[i][j].set_xlabel(xlabel[n_axis], fontdict={'fontsize': 10})
                ax[i][j].set_ylabel(ylabel[n_axis], fontdict={'fontsize': 10})
                ax[i][j].tick_params(labeltop=True, labelright=True)
                ax[i][j].set_title(titles[n_axis], fontdict={'fontsize': 10})
                fig.colorbar(img_, ax=ax[i][j], fraction=fraction, pad=0.1)
            else:
                fig.delaxes(ax[i][j])
    if title:
        plt.suptitle(title, y=y_margin, fontsize=20)
    if save_to is not None:
        plt.savefig(save_to, bbox_inches='tight', pad_inches=0)
    _ = plt.show() if show_plot else plt.close()
    return fig

# pylint: disable=too-many-arguments
def plot_slice(imgs, titles, vmins, vmaxs, cmaps, xlabel='xlines', ylabel='ilines',
                 savefig=False, show_plot=False, title=None, **kwargs):
    """Plotter for deconvlution QC metrics"""
    rows = imgs.shape[-1]

    col_size, row_size, fraction, y_margin = 14, 9, 0.021, 0.91

    fig, ax = plt.subplots(rows, 1, figsize=(col_size*1, row_size*rows))
    for n_axis in range(rows):
        img_n = imgs[:, :, n_axis]
        default_kwargs = {'cmap': cmaps[n_axis]}
        divnorm = colors.TwoSlopeNorm(vmin=vmins[n_axis], vcenter=0, vmax=vmaxs[n_axis])
        img_ = ax[n_axis].imshow(img_n, **{**default_kwargs, **kwargs}, norm=divnorm)

        ax[n_axis].set_xlabel(xlabel, fontdict={'fontsize': 10})
        ax[n_axis].set_ylabel(ylabel, fontdict={'fontsize': 10})
        ax[n_axis].tick_params(labeltop=True, labelright=True)
        ax[n_axis].set_title(titles[n_axis], fontdict={'fontsize': 10})
        fig.colorbar(img_, ax=ax[n_axis], fraction=fraction, pad=0.1)
    if title:
        plt.suptitle(title, y=y_margin, fontsize=20)
    if savefig:
        plt.savefig(savefig, bbox_inches='tight', pad_inches=0)
    _ = plt.show() if show_plot else plt.close()
    return fig


def update_avo_params(params, batch, component, bin_size, storage_size, window, horizon_window,
                      horizon, calc_method):
    """ One step of AVO.

    Parameters
    ----------
    params: array-like
        The storage contains AVO distributions from previous batches.
    batch : SeismicBatch or B() named expression.
        Current batch from pipeline.
    component: str
        Component name with shot gathers.
    bin_size: int
        Size of one bin.
    storage_size: int
        The number of amplitudes in one bin.
    window: array-like with size 2 or None
        The interval in ms where to calculate AVO. (see :meth:`~.avo_dataset.find_avo_distribution`)
    horizon_window: int or array-like with length 2
        The interval corresponds to the shift from the given horizon.
        (see :meth:`~.avo_dataset.find_avo_distribution`)
    horizon: str or None
        Path to horizon. (see :meth:`~.avo_dataset.find_avo_distribution`)
    calc_method: callable
        Method to aggregate amplitudes in one bin.
        (see `method` argument in :meth:`~.avo_dataset.find_avo_distribution`)
    Returns
    -------
        : array-like
        Storage containing all previous AVO distributions and new AVO from this batch added to the end.
    """
    for idx in batch.indices:
        pos = batch.get_pos(None, component, idx)
        field = getattr(batch, component)[pos]

        batch_df = batch.index.get_df(index=[idx])
        offset = np.sort(batch_df['offset'])
        samples = batch.meta[component]['samples']
        t_step = np.diff(samples[:2])[0]

        if horizon is not None:
            crossline, inline = batch_df[['CROSSLINE_3D', 'INLINE_3D']].iloc[0]
            window = horizon[(horizon['CROSSLINE_3D'] == crossline) & \
                             (horizon['INLINE_3D'] == inline)]['time'].iloc[0]
            lower_bound, upper_bound = horizon_window
            window = (np.array([window - lower_bound, window + upper_bound])/t_step).astype(np.int32)
            window = np.clip(window, 0, len(samples))
        if isinstance(bin_size, int):
            step_list = np.arange(0, offset[-1]+bin_size, bin_size)
        else:
            step_list = np.append(bin_size[bin_size < offset[-1]], offset[-1]+1)

        storage = np.zeros(storage_size)
        for i, stp in enumerate(step_list[:-1]):
            subfield = field[np.array(offset >= stp) & np.array(offset < step_list[i+1])]
            if subfield.size == 0:
                storage[i] = 0
                continue

            subfield = subfield[:, window[0]: window[1]+1]
            subfield[subfield == 0] = np.nan
            storage[i] = np.nan_to_num(calc_method(subfield), 0)

        params = np.array([storage]) if params is None else np.append(params, [storage], axis=0)
    return params

def load_horizon(horizon):
    """ Load horizons from file. This file should contain columns with inline, crossline
    and horizon's time for current inline and crossline.
    Columns order:   |  INLINE  |   CROSSLINE   | ...another columns... | horizon time  |

    Parameters
    ----------
    horizon : str
        path to horizon

    Returns
    -------
        : pd.DataFrame with 3 columns: INLINE_3D, CROSSLINE_3D, time.

    Note
    ----
    File shouldn't contain columns' name.
    """
    horizon_val = []
    with open(horizon) as file:
        text = file.read()
        lines = text.split('\n')
        for line in lines:
            line = re.sub('[a-zA-Z:]', ' ', line)
            line = re.sub(' +', ' ', line.strip())
            if line == '':
                continue
            line = line.split(' ')
            horizon_val.append([int(line[0]), int(line[1]), float(line[-1])])
        file.close()
    return pd.DataFrame(horizon_val, columns=['INLINE_3D', 'CROSSLINE_3D', 'time'])

def avo_plot(data, bin_size, amp_size, avg_size, avg_method='mean', is_approx=False, approx_degree=3, stats=None, # pylint: disable=too-many-statements
             figsize=(15, 7), title=None, save_to=None, dpi=100, save_bin=None, show=False, **kwargs):
    """ Plot AVO distribution for `data`. The distribution is represented by the graph from the amplitude and offset.
        Based on the offset, data is divided into bins. Each bin contains traces with a difference in offsets no more
        than `bin_size`. Blue dots correspond to RMS or modulus of average amplitude values (depends on `method`
        parameter from :meth:`~.avo_dataset.find_avo_distribution`) on a single seismogram in one bin. The red triangle
        corresponds to the average value (or any callable from `avg_method` argument) of amplitudes in a certain bin.

    Parameters
    ----------
    data: array-like
        AVO distribution with shape (Number of seismograms in the dataset, Number of bins).
    bin_size: int
        Size of one bin. Must match the size of the bin that was used when calculating the AVO distribution.
    amp_size: int
        Size of blue dots that correspond to amplitude values on a single seismogram in one bin.
        Comes directly to `matplotlib.pyplot.scatter` as `s` argument.
    avg_size: int
        Size of the red triangle that corresponds to a mean value of amplitudes in a certain bin.
        Comes directly to `matplotlib.pyplot.scatter` as `s` argument.
    avg_method: 'mean' or callable, optional, default: 'mean'
        A method for aggregating values in a bin. If "mean", then the red triangle will represent the average value of
        the amplitudes in a certain bin. Otherwise, the position of the triangle will depend on the given
        callable method.
    is_approx: bool, optional, default: False
        If True, instead of the original values of the average bins' amplitudes, their approximation will be shown.
        If False, original values of the average bins' amplitudes will be shown.
    approx_degree: int, optional, default: 3
        The degree of the polynomial for approximation comes to `np.polyfit` as `deg` argument.
    stats: 'std', 'corr', list of both, callable or None, optional, default: None
        If not None, the statistic about the given data will be shown.
        'std' - the average value of the standard deviation within each bin
        'corr' - the Pearson correlation coefficient between approximation and original average bin amplitudes.
    figsize: array-like, optional, default: (15, 7)
        Output plot size.
    title: str, optional, default: None
        Plot's title.
    save_to: str or None, optional, default: None
        If not None, save the plot to the given path.
    dpi: int, optional, default: 100
        The resolution argument for matplotlib.pyplot.savefig.
    save_bin: str or None, optional, default: None
       If not None, the resulting bins will be saved at the specified path in the DataFrame with the
       following structure:
       | bin number | average value | bin_avg_1 | ... | bin_avg_N |.


    Note
    ----
    1. If `is_approx` is True, `avg_method` will not affect the position of average values in each bin (red triangles).
    """
    transposed_data = data.T.copy()
    nan_data = transposed_data.copy()
    nan_data[nan_data == 0] = np.nan
    stats_val = []

    if avg_method == 'mean':
        avg_method = lambda nan_data: np.nanmean(nan_data, axis=1)
    elif not callable(avg_method):
        raise ValueError("`avg_method` as src should be either 'mean' or callable,"
                         f" not {avg_method}.")
    # Calculate average value for each bin.
    avg_value = avg_method(nan_data)
    avg_value = np.nan_to_num(avg_value, 0)

    # Drop empty bins.
    nonzeros = np.nonzero(avg_value)[0]
    avg_value = avg_value[nonzeros]
    transposed_data = transposed_data[nonzeros]

    if bin_size == 'offset':
        bin_size = nonzeros.copy()
    elif isinstance(bin_size, int):
        bin_size = nonzeros*bin_size

    # Calculate approximation.
    poly = np.polyfit(bin_size, avg_value, deg=approx_degree)
    avg_approx = np.polyval(poly, bin_size)

    if stats is not None:
        stats_names = []
        if isinstance(stats, str):
            stats = [stats]
        for stat in stats:
            if stat == 'std':
                stats_val.append(np.mean(np.nanstd(nan_data[nonzeros], axis=1)))
                stats_names.append('Mean std')
            elif stat == 'corr':
                stats_val.append(np.corrcoef(avg_value, avg_approx)[0][1])
                stats_names.append('Corr')
            elif hasattr(stat, '__call__'):
                stats_val.append(stat(nan_data[nonzeros]))
                stats_names.append('Callable stat')
            else:
                ValueError('Wrong stats type.')

    fig = plt.figure(figsize=figsize)
    plt.ylabel('Amplitude')
    plt.xlabel('Offset')
    plt.grid()

    if len(stats_val) > 0:
        if title is None:
            title = ''
        plt.title(title + '\n Stats: ' + ' '.join([f"{name} : {val:.06}"
                                                   for name, val in zip(stats_names, stats_val)]))
    else:
        plt.title(title)

    # Choose whether show approximation or original bins average values.
    draw_avg = avg_approx.copy() if is_approx else avg_value.copy()

    for i, (avg, bin_avg) in enumerate(zip(transposed_data, draw_avg)):
        avg = avg[np.nonzero(avg)]
        plt.scatter(np.zeros(avg.shape)+bin_size[i], avg,
                    color='C0', marker='o', s=amp_size, **kwargs)
        plt.scatter([bin_size[i]], bin_avg, color='r', marker='v', s=avg_size)

    if save_to is not None:
        plt.savefig(save_to, dpi=dpi)

    if save_bin is not None:
        save_bin = save_bin if len(save_bin.split('.')) == 2 else save_bin + '.csv'
        df_bin = pd.DataFrame([bin_size, draw_avg], columns=['bin', 'bin_avg'])
        for i, n_data in enumerate(transposed_data):
            df_bin['bin_avg_{}'.format(i)] = n_data
        df_bin.to_csv(save_bin, index=False)
    if show:
        plt.show()
    return fig

def std_plot(avo_results, bin_size, names=None, figsize=(15, 10), align_mean=False, save_to=None,
             dpi=100, title=None, show=False, **kwargs):
    """ Plot standard deviation for given AVO or list of AVOs.

    Parameters
    ----------
    avo_results: array-like or list of array-like
        AVO distribution(s).
    bin_size: int
        Size of one bin. Must match the size of the bin that was used when calculating the AVO distribution.
    names: list of str or None
        Names for each AVO distribution will be shown on the plot. If None, each distribution will be assigned a number
        starting from zero.
    figsize: array-like, optional, default: (15, 10)
        Output plot size.
    align_mean: bool, optional, default: False
        If True, all AVOs will be plotted with the same mean values. Note that this shift does not affect the relative
        values of the AVO distributions.
    save_to: str or None, optional
        If not None, save the plot to the given path.
    dpi: int, optional, default: None
        The resolution argument for matplotlib.pyplot.savefig.
    title: str, optional, default: None
        Plot's title.
    """
    _ = kwargs
    sns.set_style("darkgrid")
    resulted_df = pd.DataFrame(columns=['val', 'indices', 'name'])

    if names is None:
        names = np.arange(len(avo_results)).astype(str)
    # Add all given AVO to DataFrame in following structure:
    # rms value of one seismogram for current bin; corresponding bin; given name;
    # During rendering, different AVO will be grouped by the name.
    for results, name in zip(avo_results, names):
        results = results.T

        nonzeros_ixs = np.nonzero(np.sum(results, axis=1))[0]
        offsets = nonzeros_ixs * bin_size
        values = results[nonzeros_ixs].reshape(-1)
        nonzeros_res = np.where(values)
        nonzeros_val = values[nonzeros_res]
        nonzeros_off = offsets.repeat(results.shape[1])[nonzeros_res]

        tmp_df = pd.DataFrame(np.array([nonzeros_val, nonzeros_off, [name]*len(nonzeros_val)]).T,
                              columns=['val', 'indices', 'name'])
        resulted_df = resulted_df.append(tmp_df)

    resulted_df.indices = resulted_df.indices.astype(float)
    resulted_df.val = resulted_df.val.astype(float)

    if align_mean:
        # Сalculate the total average for all values in DataFrame and change the values
        # for each AVO by the difference between total average and average for current AVO result.
        gen_mean = np.mean(resulted_df.val)
        for name, dframe in resulted_df.groupby('name'):
            align = gen_mean - np.mean(dframe.val)
            resulted_df.loc[resulted_df['name'] == name, 'val'] = dframe.val + align

    fig = plt.figure(figsize=figsize)
    plt.title(title)
    plt.xlabel('Offset')
    plt.ylabel('Amplitude')
    sns.lineplot(x='indices', y='val', hue='name', data=resulted_df, ci='sd')
    sns.set_style("ticks")

    if save_to is not None:
        plt.savefig(save_to, dpi=dpi)
    if show:
        plt.show()
    return fig
