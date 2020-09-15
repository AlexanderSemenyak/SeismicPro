"""File contains metircs for seismic processing."""
import numpy as np
from numba import njit, prange
from scipy import stats

from .plot_utils import plot_metrics_map

from ..batchflow import action, inbatch_parallel
from ..batchflow.models.metrics import Metrics

METRICS_ALIASES = {
    'map': 'construct_map'
}

class SemblanceMetrics:
    """"Semblance metrics class"""

    @staticmethod
    @inbatch_parallel(init="_init_component", target="threads")
    def calculate_minmax(batch, index, src, dst):
        """some docs"""
        pos = batch.get_pos(None, src, index)
        semblance = getattr(batch, src)[pos]
        getattr(batch, dst)[pos] = np.max(np.max(semblance, axis=1) - np.min(semblance, axis=1))
        return batch

    @staticmethod
    @inbatch_parallel(init="_init_component", target="threads")
    def calculate_std(batch, index, src, dst):
        """some docs"""
        pos = batch.get_pos(None, src, index)
        semblance = getattr(batch, src)[pos]
        getattr(batch, dst)[pos] = np.max(np.std(semblance, axis=1))
        return batch

class PM:
    @staticmethod
    @inbatch_parallel(init="_init_component", target="threads")
    def velocity(batch, index, dst ,src_picking='picking', src_offset='offset'):
        """some docs"""
        pos = batch.get_pos(None, src_picking, index)
        time = getattr(batch, src_picking)[pos]
        offset = getattr(batch, src_offset)[pos]
        mask = [time > 1]
        time = time[mask]
        offset = offset[mask]
        getattr(batch, dst)[pos] = np.mean(offset / time)
        return batch

    @staticmethod
    @inbatch_parallel(init="_init_component", target="f")
    def linear_diff(batch, index, dst, src_raw='raw', src_picking='picking', src_offset='offset', src_gx='GroupX', src_gy='GroupY', src_sx='SourceX',
                 src_sy='SourceY', src_source_elev='SourceElevation', src_group_elev='GroupElevation'):
        """some docs"""
        pos = batch.get_pos(None, src_picking, index)
        raw = getattr(batch, src_raw)[pos]
        time = getattr(batch, src_picking)[pos]
        offset = getattr(batch, src_offset)[pos]
        gx, gy, sx, sy = getattr(batch, src_gx)[pos], getattr(batch, src_gy)[pos], getattr(batch, src_sx)[pos], getattr(batch, src_sy)[pos]
        s_elev, g_elev = getattr(batch, src_source_elev)[pos], getattr(batch, src_group_elev)[pos] 
        offset_all = np.sqrt((gx - sx) ** 2 + (gy - sy) ** 2 + (s_elev - g_elev) ** 2)
        slope, intercept  = stats.siegelslopes(time, offset)
        values  = abs(offset * slope + intercept - time)
        time_for_elev = abs((offset - offset_all) * slope)
        getattr(batch, dst[0])[pos] = np.mean(values)
        getattr(batch, dst[1])[pos] = np.mean(time_for_elev)
        return batch
    


class MetricsMap(Metrics):
    """seismic metrics class"""
    def __init__(self, metrics, coords, *args, **kwargs):
        _ = args, kwargs
        super().__init__()

        self.metrics = metrics
        unique_coords, position = np.unique(coords, axis=0, return_index=True)
        self.coords = unique_coords[np.argsort(position)]
        self._maps_list = [[*coord, metric] for coord, metric in zip(self.coords, self.metrics)]

        self._agg_fn_dict = {'mean': np.nanmean,
                             'max': np.nanmax,
                             'min': np.nanmin}

    @property
    def maps_list(self):
        """get map list"""
        return self._maps_list

    def append(self, metrics):
        """append"""
        self._maps_list.extend(metrics._maps_list)

    def __getattr__(self, name):
        if name == "METRICS_ALIASES":
            raise AttributeError # See https://nedbatchelder.com/blog/201010/surprising_getattr_recursion.html
        name = METRICS_ALIASES.get(name, name)
        return object.__getattribute__(self, name)

    def __split_result(self):
        """split_result"""
        coords_x, coords_y, metrics = np.array(self._maps_list).T
        metrics = np.array(list(metrics), dtype=np.float32)
        return np.array(coords_x, dtype=np.float32), np.array(coords_y, dtype=np.float32), metrics

    def construct_map(self, bin_size=500, max_value=None, title=None, figsize=None, save_dir=None, pad=False, plot=True):
        """Each value in resulted map represent average value of metrics for coordinates belongs to current bin."""
        coords_x, coords_y, metrics = self.__split_result()
        metric_map = self.construct_metrics_map(coords_x=coords_x, coords_y=coords_y, metrics=metrics, bin_size=bin_size)
        extent_coords = [coords_x.min(), coords_x.max(), coords_y.min(), coords_y.max()]
        if plot:
            plot_metrics_map(metrics_map=metric_map, max_value=max_value, extent_coords=extent_coords,
                            title=title, figsize=figsize, save_dir=save_dir, pad=pad)
        return metric_map

    @staticmethod
    @njit(parallel=True)
    def construct_metrics_map(coords_x, coords_y, metrics, bin_size):
        """njit map"""
        range_x = np.arange(coords_x.min(), coords_x.max() + bin_size, bin_size)
        range_y = np.arange(coords_y.min(), coords_y.max() + bin_size, bin_size)
        metrics_map = np.full((len(range_y), len(range_x)), np.nan)

        for i in prange(len(range_x)):
            for j in prange(len(range_y)):
                mask = ((coords_x - range_x[i] >= 0) & (coords_x - range_x[i] < bin_size) &
                        (coords_y - range_y[j] >= 0) & (coords_y - range_y[j] < bin_size))
                if mask.sum() > 0:
                    metrics_map[j, i] = metrics[mask].mean()
        return metrics_map
