from __future__ import annotations

import html

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...pipeline.segmentation import segment
from ...pipeline.segmentation.mask_store import MaskStore
from ...pipeline.segmentation.segmenter_registry import SegmenterRegistry
from ...support.cache_folder import CacheFolder
from ...support.image_fetcher import ImageFetcher
from .cache_card import CacheCard
from .download_dialog import DownloadDialog
from .model_card import ModelCard
from .model_info import MB, ModelInfo, ui_log


class CachePage(QWidget):
    """The Models and cache page of the Preferences window: the cache folder, which
    background-removal models are downloaded (with actions on them), and papermini's
    other cached files (masks, images from links), which it can clear. The content
    scrolls when the window is too small for it. ``segmenters`` and ``masks`` keep the
    models and masks, ``images_from_web`` the images downloaded from links.
    ``in_use()`` gives the image files of the open figures, which clearing keeps."""

    changed = Signal(str)  # a model was downloaded or deleted

    def __init__(
        self,
        segmenters: SegmenterRegistry,
        masks: MaskStore,
        images_from_web: ImageFetcher,
        parent=None,
        in_use=lambda: (),
    ):
        super().__init__(parent)
        self._segmenters = segmenters
        self._masks = masks
        self._images_from_web = images_from_web
        self.in_use = in_use
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("CacheScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("CacheContent")
        v = QVBoxLayout(content)
        v.setContentsMargins(0, 0, 12, 6)  # (room for the scroll bar)
        v.setSpacing(10)

        v.addWidget(ModelInfo.label("Models and cache", "DialogTitle", wrap=False))
        about = ModelInfo.label(
            "papermini keeps its downloaded models and other cached files in "
            "one folder.",
            "Muted",
        )
        v.addWidget(about)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.folder = ModelInfo.label(html.escape(str(CacheFolder.path())), "Hint")
        self.folder.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        btn_open = QPushButton("Open folder")
        btn_open.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(CacheFolder.path()))
            )
        )
        self.btn_all = QPushButton("Clear cache…")
        self.btn_all.setToolTip(
            "Delete everything in the cache folder: the downloaded "
            "models, the masks and the images from links"
        )
        self.btn_all.clicked.connect(self.delete_all)
        top.addWidget(self.folder, 1)
        top.addWidget(btn_open, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.btn_all, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addLayout(top)

        v.addSpacing(10)
        v.addWidget(
            ModelInfo.label("Background-removal models", "PageSection", wrap=False)
        )
        v.addWidget(
            ModelInfo.label(
                "Models are downloaded once and kept on this computer. Delete one to free disk "
                "space: papermini asks before downloading it again when you next use it.",
                "Muted",
            )
        )
        v.addSpacing(4)
        self.cards = {m: ModelCard(m, self) for m in segment.ONNX_MODELS}
        for card in self.cards.values():
            v.addWidget(card)

        v.addSpacing(10)
        v.addWidget(ModelInfo.label("Other cached files", "PageSection", wrap=False))
        v.addWidget(
            ModelInfo.label(
                "papermini keeps these to open figures quickly. Clear them to "
                "free disk space: papermini makes or downloads them again "
                "when it needs them.",
                "Muted",
            )
        )
        self.masks = CacheCard(
            "Masks",
            "The background removal of each image, so a figure need not run "
            "the model again.",
            self.clear_masks,
        )
        self.images = CacheCard(
            "Images from links",
            "The images of figures added from a link. Images that "
            "open figures use are kept.",
            self.clear_images,
        )
        v.addWidget(self.masks)
        v.addWidget(self.images)
        v.addStretch(1)
        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area, 1)
        self.refresh_cache()

    def download(self, model: str):
        DownloadDialog(
            model,
            self._segmenters,
            self,
            ask=False,
            force=self._segmenters.path(model).exists(),
        ).exec()
        self.cards[model].refresh()
        self.refresh_cache()
        if self._segmenters.path(model).exists():
            self.changed.emit(model)

    def delete(self, model: str):
        spec = segment.ONNX_MODELS[model]
        ok = QMessageBox.question(
            self,
            "Delete model",
            f"Delete {spec.title}? papermini asks to download it again "
            f"(about {spec.mb} MB) the next time a figure needs it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if ok != QMessageBox.StandardButton.Yes:
            return
        ui_log.info("Deleting the %s model", model)
        try:
            self._segmenters.delete(model)
        except OSError as e:
            ui_log.warning("Could not delete the %s model: %s", model, e)
            QMessageBox.warning(self, "Delete model", f"Could not delete the file: {e}")
        self.cards[model].refresh()
        self.refresh_cache()
        self.changed.emit(model)

    def _kept(self) -> list:
        """The downloaded images that open figures use."""
        folder = self._images_from_web.cached_images()
        use = {str(p) for p in self.in_use()}
        return [p for p in folder if str(p) in use]

    def refresh_cache(self):
        masks = self._masks.files()
        self.masks.show_state(
            f"{self._count(len(masks), 'mask', 'masks')} · {self._size(masks)}"
            if masks
            else "No masks",
            bool(masks),
        )
        images, kept = self._images_from_web.cached_images(), self._kept()
        text = (
            f"{self._count(len(images), 'image', 'images')} · {self._size(images)}"
            if images
            else "No images"
        )
        if kept:
            text += f" · {len(kept)} in use by open figures"
        self.images.show_state(text, len(images) > len(kept))
        self.btn_all.setEnabled(
            bool(self._downloaded() or masks or len(images) > len(kept))
        )

    def _downloaded(self) -> list:
        """The built-in models that are downloaded."""
        return [m for m in segment.ONNX_MODELS if self._segmenters.path(m).exists()]

    def delete_all(self):
        """Delete the downloaded models, the masks and the images from links (except
        those open figures use), after asking."""
        models = self._downloaded()
        kept = set(map(str, self._kept()))
        files = (
            [self._segmenters.path(m) for m in models]
            + self._masks.files()
            + [p for p in self._images_from_web.cached_images() if str(p) not in kept]
        )
        ok = QMessageBox.question(
            self,
            "Clear cache",
            f"Clear the whole cache ({self._size(files)})? This also deletes the downloaded "
            "models, not only the masks and images from links."
            "\n\npapermini asks before downloading a model again, the next time a figure "
            "needs it. Images that open figures use are kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if ok != QMessageBox.StandardButton.Yes:
            return
        ui_log.info("Clearing the whole cache")
        failed = []
        for m in models:
            try:
                self._segmenters.delete(m)
            except OSError as e:
                failed.append(f"{self._segmenters.path(m).name}: {e}")
        self._masks.clear()
        self._images_from_web.clear_images(keep=self._kept())
        for card in self.cards.values():
            card.refresh()
        self.refresh_cache()
        for m in models:
            self.changed.emit(m)
        if failed:
            ui_log.warning("Could not delete: %s", "; ".join(failed))
            QMessageBox.warning(
                self, "Clear cache", "Could not delete:\n" + "\n".join(failed)
            )

    def clear_masks(self):
        ui_log.info("Cleared %d cached mask(s)", self._masks.clear())
        self.refresh_cache()

    def clear_images(self):
        ui_log.info(
            "Cleared %d downloaded image(s)",
            self._images_from_web.clear_images(keep=self._kept()),
        )
        self.refresh_cache()

    @staticmethod
    def _size(files) -> str:
        """Return the total size of ``files``, in MB (with a decimal below 10 MB)."""
        total = 0
        for f in files:
            try:
                total += f.stat().st_size
            except OSError:
                pass
        mb = total / MB
        return f"{mb:.1f} MB" if mb < 10 else f"{mb:.0f} MB"

    @staticmethod
    def _count(n: int, one: str, many: str) -> str:
        return f"{n} {one if n == 1 else many}"
