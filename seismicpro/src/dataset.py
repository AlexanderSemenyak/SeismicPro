"""Implements SeismicDataset class that allows iterating over gathers in surveys by generating small subsets of data
called batches"""

from textwrap import dedent

import numpy as np

from .batch import SeismicBatch
from .index import SeismicIndex
from ..batchflow import Dataset


class SeismicDataset(Dataset):
    """A dataset, that generates batches of `SeismicBatch` class. Contains identifiers of seismic gathers from a
    survey or a group of surveys and a specific `batch_class` to create and process small subsets of data.

    Usually, gather identification in a dataset is done using a :class:`~index.SeismicIndex`, which is constructed on
    dataset creation if was not passed directly. Most of the :class:`~dataset.SeismicDataset` arguments are passed to a
    :func:`~index.SeismicIndex.__init__` as is so please refer to its documentation to learn more about gather
    indexing.

    Examples
    --------
    Let's consider a survey we want to process:
    >>> survey = Survey(path, header_index="FieldRecord", header_cols=["TraceNumber", "offset"], name="survey")

    In most cases, dataset creation is identical to that of :class:`~index.SeismicIndex`:
    >>> dataset = SeismicDataset(surveys=survey)

    Similar to the :class:`~index.SeismicIndex` several surveys can be combined together either by merging or
    concatenating. After the dataset is created, a subset of gathers can be obtained via
    :func:`~SeismicDataset.next_batch` method:
    >>> batch = dataset.next_batch(10)

    Here a batch of 10 gathers was created and can now be processed using the methods defined in
    :class:`~batch.SeismicBatch`. The batch does not contain any data yet and gather loading is usually the first
    method you want to apply:
    >>> batch.load(src="survey")

    Note, that here we've specified the name of the survey we want to obtain gathers from.

    Parameters
    ----------
    index : DatasetIndex or None, optional
        Unique identifiers of seismic gathers in a dataset. If `index` is not given, it is constructed by instantiating
        a :class:`~index.SeismicIndex` with passed `surveys`, `mode` and `kwargs`.
    surveys : Survey or list of Survey, optional
        Surveys to use to construct an index.
    mode : {"c", "concat", "m", "merge", None}, optional, defaults to None
        A mode used to combine multiple surveys into an index. If `None`, only a single survey can be passes to a
        `surveys` arg.
    batch_class : type, optional, dafaults to SeismicBatch
        A class of batches, generated by a dataset. Must be inherited from :class:`~batchflow.Batch`.
    kwargs : misc, optional
        Additional keyword arguments to `SeismicIndex.__init__`.
    """
    def __init__(self, index=None, surveys=None, mode=None, batch_class=SeismicBatch, **kwargs):
        if index is None:
            index = SeismicIndex(surveys=surveys, mode=mode, **kwargs)
        super().__init__(index, batch_class=batch_class, **kwargs)

    def __str__(self):
        """Print dataset metadata including information about its index and batch class."""
        msg = dedent(f"""
        Dataset index:             {self.index.__class__}
        Batch class:               {self.batch_class}

        """)
        if isinstance(self.index, SeismicIndex):
            msg += self.index._get_index_info(indents='', prefix='dataset.index')
            for survey_name, survey_list in self.index.surveys_dict.items():
                for concat_id, survey in enumerate(survey_list):
                    msg += f"\n{'_'*79}\nSurvey named '{survey_name}' with CONCAT_ID {concat_id}.\n" + str(survey)
        else:
            msg += str(self.index)
        return msg

    def info(self):
        """Print dataset metadata including information about its index and batch class."""
        print(self)

    def create_subset(self, index):
        """Return a new dataset object based on the subset of indices given.

        Notes
        -----
        During the call subset of `self.index.headers` is calculated which may take a while for large indices.

        Parameters
        ----------
        index : SeismicIndex or pd.MultiIndex
            Index values of the subset to create a new `SeismicDataset` object for.

        Returns
        -------
        subset : SeismicDataset
            A subset of the dataset.
        """
        if not isinstance(index, SeismicIndex):
            index = self.index.create_subset(index)
        return type(self).from_dataset(self, index)

    def collect_stats(self, n_quantile_traces=100000, quantile_precision=2, stats_limits=None, bar=True):
        """Collect the following trace data statistics for each survey in the dataset:
        1. Min and max amplitude,
        2. Mean amplitude and trace standard deviation,
        3. Approximation of trace data quantiles with given precision,
        4. The number of dead traces.

        Since fair quantile calculation requires simultaneous loading of all traces from the file we avoid such memory
        overhead by calculating approximate quantiles for a small subset of `n_quantile_traces` traces selected
        randomly. Moreover, only a set of quantiles defined by `quantile_precision` is calculated, the rest of them are
        linearly interpolated by the collected ones.

        After the method is executed `has_stats` flag is set to `True` and all the calculated values can be obtained
        via corresponding attributes for all the surveys in the dataset.

        Examples
        --------
        Statistics calculation for the whole dataset can be done as follows:
        >>> survey = Survey(path, header_index="FieldRecord", header_cols=["TraceNumber", "offset"], name="survey")
        >>> dataset = SeismicDataset(surveys=survey).collect_stats()

        After a train-test split is performed, `train` and `test` parts of the dataset share lots of their attributes
        allowing for `collect_stats` to be used to calculate statistics for the training set and be available for
        gathers in the testing set avoiding data leakage during machine learning model training:
        >>> dataset.split()
        >>> dataset.train.collect_stats()
        >>> dataset.test.next_batch(1).load(src="survey").scale_standard(src="survey", use_global=True)

        But note that if no gathers from a particular survey were included in the training set its stats won't be
        collected!

        Parameters
        ----------
        n_quantile_traces : positive int, optional, defaults to 100000
            The number of traces to use for quantiles estimation.
        quantile_precision : positive int, optional, defaults to 2
            Calculate an approximate quantile for each q with `quantile_precision` decimal places.
        stats_limits : int or tuple or slice, optional
            Time limits to be used for statistics calculation. `int` or `tuple` are used as arguments to init a `slice`
            object. If not given, whole traces are used. Measured in samples.
        bar : bool, optional, defaults to True
            Whether to show a progress bar.

        Returns
        -------
        dataset : SeismicDataset
            A dataset with collected stats. Sets `has_stats` flag to `True` and updates statistics attributes inplace
            for each of the underlying surveys.
        """
        concat_ids = self.indices.get_level_values(0)
        indices = self.indices.droplevel(0)
        for concat_id in np.unique(concat_ids):
            concat_id_indices = indices[concat_ids == concat_id]
            for survey_list in self.index.surveys_dict.values():
                survey_list[concat_id].collect_stats(indices=concat_id_indices, n_quantile_traces=n_quantile_traces,
                                                     quantile_precision=quantile_precision, stats_limits=stats_limits,
                                                     bar=bar)
        return self
