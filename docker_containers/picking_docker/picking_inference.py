""" Inference script that takes segy file and First break picking model,
predicts picking for traces and dump them to csv file.
"""
import os
import sys
import argparse

import numpy as np

sys.path.append('../..')

from seismicpro.batchflow import B, Pipeline
from seismicpro.batchflow.models.torch import UNet # pylint: disable=import-error
from seismicpro.src import TraceIndex, SeismicDataset

def make_prediction():
    """ Read the model and data paths and run inference pipeline.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--path_raw', type=str, help="Path to SEGY file.",
                        required=True)
    parser.add_argument('-m', '--path_model', type=str, help="Path to trained model.",
                        required=True)
    parser.add_argument('-d', '--path_dump', type=str, help="Path to CSV file where \
                        the results would be stored.", default='dump.csv')
    parser.add_argument('-n', '--num_zero', type=int, help="Required number of zero \
                        values for the trace to contain to droped.", default=100)
    parser.add_argument('-bs', '--batch_size', type=int, help="The number of traces in \
                        the batch for inference stage.", default=1000)
    parser.add_argument('-ts', '--trace_len', type=int, help="The number of first samples \
                        of the trace to load.", default=1000)
    parser.add_argument('-dvc', '--device', type=str, help="The device for \
                        inference. Can be 'cpu' or 'gpu'.", default='cpu')
    parser.add_argument('-s', '--shift', type=float, help="Picking time phase shift", default=0)
    args = parser.parse_args()
    path_raw = args.path_raw
    model = args.path_model
    save_to = args.path_dump
    num_zero = args.num_zero
    batch_size = args.batch_size
    trace_len = args.trace_len
    device = args.device
    shift = args.shift
    predict(path_raw, model, num_zero, save_to, batch_size, trace_len, device, shift)

def predict(path_raw, path_model, num_zero=100, save_to='dump.csv',
            batch_size=1000, trace_len=1000, device='cpu', shift=0):
    """Make predictions and dump results using loaded model and path to data.

    Parameters
    ----------
    path_raw: str
        Path to SEGY file.
    path_model: str
        Path to the file with trained model.
    num_zero: int, default: 100
        Reauired number of zero values in a row in the trace to drop such trace.
    save_to: str, default: 'dump.csv'
        Path to CSV file where the results will be stored.
    bs: int, default: 1000
        The batch size for inference.
    trace_len: int, default: 1000
        The number of first samples in the trace to load to the pipeline.
    device: str or torch.device, default: 'cpu'
        The device used for inference. Can be 'gpu' in case of avaliavle GPU.
    shift: float, default: 0
        Shift the picking times for each trace on the given phase shift, measured in radians.

    """
    data = SeismicDataset(TraceIndex(name='raw', path=path_raw))

    config_predict = {
        'build': False,
        'load/path': path_model,
        'device': device
    }

    try:
        os.remove(save_to)
    except OSError:
        pass

    test_tmpl = (data.p
                 .init_model('dynamic', UNet, 'my_model', config=config_predict)
                 .load(components='raw', fmt='segy', tslice=slice(0, trace_len))
                 .drop_zero_traces(num_zero=num_zero, src='raw')
                 .standardize(src='raw', dst='raw')
                 .add_components(components='predictions')
                 .call(lambda batch: np.stack(batch.raw), save_to=B('raw'))
                 .predict_model('my_model', B('raw'), fetches='predictions',
                                save_to=B('predictions', mode='a'))
                 .mask_to_pick(src='predictions', dst='predictions', labels=False)
                )
    if shift:
        test_tmpl += Pipeline().shift_pick_phase(src='predictions', dst='predictions', src_traces='raw', shift=shift)

    test_pipeline = test_tmpl + Pipeline().dump(src='predictions', fmt='picks', path=save_to, src_traces='raw')
    test_pipeline.run(batch_size, n_epochs=1, drop_last=False, shuffle=False, bar=True)

if __name__ == "__main__":
    sys.exit(make_prediction())
