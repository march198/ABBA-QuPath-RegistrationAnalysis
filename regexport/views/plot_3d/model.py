from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
import pandas as pd
from PyQt5.QtCore import QThreadPool
from bg_atlasapi import BrainGlobeAtlas
from matplotlib import pyplot as plt
from matplotlib.colors import ListedColormap
from traitlets import HasTraits, Instance, directional_link

from regexport.data.filters import is_parent
from regexport.model import AppState
from regexport.utils.parallel import Task
from regexport.utils.profiling import warn_if_slow


@dataclass(frozen=True)
class PointCloud:
    coords: np.ndarray = field(default=np.empty((0, 3), dtype=float))
    colors: np.ndarray = field(default=np.empty((0, 3), dtype=float))
    alphas: np.ndarray = field(default=np.empty((0, 1), dtype=float))

    def __post_init__(self):
        assert self.coords.ndim == 2 and self.coords.shape[1] == 3
        assert self.colors.ndim == 2 and self.colors.shape[1] == 3
        assert self.alphas.ndim == 2 and self.alphas.shape[1] == 1


class PlotterModel(HasTraits):
    atlas_mesh = Instance(Path, allow_none=True)
    points = Instance(PointCloud, default_value=PointCloud())

    def register(self, model: AppState):
        self.model = model
        directional_link(
            (model, 'atlas'),
            (self, 'atlas_mesh'),
            lambda atlas: Path(str(atlas.structures[997]['mesh_filename'])) if atlas is not None else None
        )
        model.observe(self.link_cells_to_points, names=[
            'selected_cell_ids', 'cells', 'selected_colormap'
        ])

    def link_cells_to_points(self, change):
        model = self.model
        worker = Task(
            self.plot_cells,
            cells=model.cells,
            selected_cell_ids=model.selected_cell_ids,
            cmap=self.model.selected_colormap
        )
        worker.signals.finished.connect(partial(setattr, self, "points"))
        pool = QThreadPool.globalInstance()
        pool.start(worker)

    @staticmethod
    @warn_if_slow()
    def plot_cells(cells: Optional[pd.DataFrame], selected_cell_ids: Optional[Tuple[int]], cmap: str = 'tab20c') -> PointCloud:
        if cells is None:
            return PointCloud()
        print('plotting')
        df = cells.copy(deep=False)
        print(df.head(), df.columns, sep='\n')
        cmap: ListedColormap = getattr(plt.cm, cmap)
        df[['red', 'green', 'blue', 'alpha']] = pd.DataFrame(cmap((codes := df.BrainRegion.cat.codes) / codes.max())[:, :4])
        if selected_cell_ids is not None:
            df = df.iloc[selected_cell_ids]
            if len(df) == 0:
                return PointCloud()

        points = PointCloud(
            coords=df[['X', 'Y', 'Z']].values * 1000,
            colors=df[['red', 'green', 'blue']].values,
            alphas=df[['alpha']].values,
        )
        return points