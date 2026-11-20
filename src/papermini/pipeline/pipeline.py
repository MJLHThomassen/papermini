from __future__ import annotations

from ..support.font_library import FontLibrary
from ..support.stage_caches import StageCaches
from .art_composer import ArtComposer
from .back_mirror import BackMirror
from .bleed_painter import BleedPainter
from .cut_path_tracer import CutPathTracer
from .debug_writer import DebugWriter
from .figure_masker import FigureMasker
from .figure_scaler import FigureScaler
from .font_checker import FontChecker
from .image_adjuster import ImageAdjuster
from .image_loader import ImageLoader
from .layout_builder import LayoutBuilder
from .mask_cleaner import MaskCleaner
from .mini_builder import MiniBuilder
from .morphology import Morphology
from .segmentation.background_remover import BackgroundRemover
from .segmentation.cancellation import Cancellation
from .segmentation.downloader import Downloader
from .segmentation.mask_store import MaskStore
from .segmentation.onnx_segmenter import OnnxSegmenter
from .segmentation.segmenter_registry import SegmenterRegistry
from .token_builder import TokenBuilder
from .token_framer import TokenFramer
from .token_renderer import TokenRenderer


class Pipeline:
    """The pipeline's services, created once and wired together. An entry point makes
    one and passes on the services its code uses.

    ``fonts`` are the fonts the pieces' text is measured in. ``downloader`` downloads
    the models and ``make_segmenter`` makes a segmenter from a model file; tests pass
    fakes.
    """

    def __init__(
        self,
        fonts: FontLibrary,
        downloader: Downloader | None = None,
        make_segmenter=OnnxSegmenter,
    ):
        self.caches = StageCaches()

        # background removal
        self.cancellation = Cancellation()
        self.segmenters = SegmenterRegistry(
            downloader or Downloader(), self.cancellation, make_segmenter
        )
        self.masks = MaskStore()
        self.images = ImageLoader()
        self.remover = BackgroundRemover(
            self.images, self.segmenters, self.masks, self.cancellation
        )

        # masks, layouts and cut paths
        self.morphology = Morphology()
        self.cleaner = MaskCleaner(self.morphology)
        self.masker = FigureMasker(
            self.images, self.remover, self.cleaner, self.cancellation, self.caches
        )
        self.scaler = FigureScaler(self.morphology)
        self.adjuster = ImageAdjuster()
        self.composer = ArtComposer(self.morphology)
        self.layouts = LayoutBuilder(
            self.morphology, self.scaler, self.composer, BackMirror(self.morphology)
        )
        self.tracer = CutPathTracer()
        self.bleed = BleedPainter(self.morphology)
        self.font_checker = FontChecker(fonts)

        # the pieces
        self.minis = MiniBuilder(
            self.morphology,
            fonts,
            self.font_checker,
            self.masker,
            self.scaler,
            self.adjuster,
            self.layouts,
            self.tracer,
            self.bleed,
            DebugWriter(self.morphology),
            self.cancellation,
            self.caches,
        )
        self.framer = TokenFramer()
        self.tokens = TokenBuilder(
            self.morphology,
            self.font_checker,
            self.masker,
            TokenRenderer(
                self.morphology, self.framer, self.adjuster, self.composer, self.bleed
            ),
            self.caches,
        )
