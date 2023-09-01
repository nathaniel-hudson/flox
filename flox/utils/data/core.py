import matplotlib as mpl
import numpy as np

from collections import defaultdict
from matplotlib.axes import Axes
from scipy import stats
from torch.utils.data import Dataset, DataLoader, Subset
from typing import Mapping, NewType, Optional, Union

from flox.flock import FlockNodeID, FlockNode, Flock

FederatedDataset = NewType(
    "FederatedDataset", Mapping[FlockNodeID, Union[Dataset, Subset]]
)


def federated_split(
    data: Dataset,
    flock: Flock,
    num_labels: int,
    samples_alpha: float = 1.0,
    labels_alpha: float = 1.0,
) -> FederatedDataset:
    """Splits up Datasets across worker nodes in a Flock using Dirichlet distributions for IID and non-IID settings.

    It is recommended to use an alpha value of 1.0 for either `samples_alpha` want non-IID number of samples across
    workers. Setting this alpha value to be < 1 will result in extreme cases where many workers will have 0 data
    samples.

    Args:
        data (Dataset): ...
        workers (Flock): ...
        num_labels (int): ...
        samples_alpha (float): ...
        labels_alpha (float): ...

    Returns:

    """
    assert samples_alpha > 0
    assert labels_alpha > 0

    num_workers = len(list(flock.workers))
    sample_distr = stats.dirichlet(np.full(num_workers, samples_alpha))
    label_distr = stats.dirichlet(np.full(num_labels, labels_alpha))

    num_samples_for_workers = (sample_distr.rvs()[0] * len(data)).astype(int)
    num_samples_for_workers = {
        worker.idx: num_samples
        for worker, num_samples in zip(flock.workers, num_samples_for_workers)
    }
    label_probs = {w.idx: label_distr.rvs()[0] for w in flock.workers}

    indices: dict[int, list[int]] = defaultdict(list)
    loader = DataLoader(data, batch_size=1)
    worker_samples = defaultdict(int)
    for idx, batch in enumerate(loader):
        _, y = batch
        label = y.item()

        probs = []
        temp_workers = []
        for w in flock.workers:
            if worker_samples[w.idx] < num_samples_for_workers[w.idx]:
                probs.append(label_probs[w.idx][label])
                temp_workers.append(w.idx)
        probs = np.array(probs)
        probs = probs / probs.sum()

        if len(temp_workers) > 0:
            chosen_worker = np.random.choice(temp_workers, p=probs)
            indices[chosen_worker].append(idx)
            worker_samples[chosen_worker] += 1

    subsets = {w.idx: Subset(data, indices[w.idx]) for w in flock.workers}
    return subsets


def fed_barplot(
    fed_data: FederatedDataset,
    num_labels: int,
    width: float = 0.5,
    ax: Optional[Axes] = None,
):
    label_counts_per_worker = {
        label: np.zeros(len(fed_data), dtype=np.int32) for label in range(num_labels)
    }

    for idx, (worker, subset) in enumerate(fed_data.items()):
        loader = DataLoader(subset, batch_size=1)
        for batch in loader:
            _, y = batch
            label = y.item()
            label_counts_per_worker[label][idx] += 1

    if ax is None:
        fig, ax = mpl.pyplot.subplots()

    bottom = np.zeros(len(fed_data))
    workers = list(range(len(fed_data)))
    for label, worker_count in label_counts_per_worker.items():
        p = ax.bar(workers, worker_count, width, label=label, bottom=bottom)
        bottom += worker_count

    return ax
