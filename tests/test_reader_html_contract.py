from pathlib import Path


def test_reader_uses_safe_markdown_renderer_and_three_pane_layout() -> None:
    html = Path("src/api/static/index.html").read_text(encoding="utf-8")

    assert "renderSafeMarkdown" in html
    assert "sanitizeHtml" in html
    assert "ocrPane" in html
    assert "translationPane" in html
    assert "leftTabPdf" in html
    assert "rightTabPdf" in html
    assert "pdfPane" not in html
    assert "typesetMath" in html
    assert "math-block" in html
    assert "rewriteAssetUrls" in html
    assert "图像资源丢失；重新执行 OCR 以重新生成" in html
    assert "correctedMarkdown" in html
    assert "saveCorrectionBtn" in html
    assert "deleteDocument" in html
    assert "删除" in html
    assert "annotationPanel" in html
    assert "createAnnotation" in html
    assert "deleteAnnotation" in html
    assert "syncLinkedBlock" in html
    assert "data-block-index" in html
    assert "annotateReadableBlocks" in html
    assert "scrollIntoView" in html
    assert "readingModeToggle" in html
    assert "showRawOcr" in html
    assert "reader_markdown" in html
    assert "getDisplayMarkdown" in html
    assert "ocr-icon-image" in html
    assert "normalizeReaderImages" in html


def test_reader_vendors_mathjax_chtml_fonts_locally() -> None:
    font_dir = Path("src/api/static/vendor/mathjax/output/chtml/fonts/woff-v2")
    expected_fonts = {
        "MathJax_AMS-Regular.woff",
        "MathJax_Calligraphic-Bold.woff",
        "MathJax_Calligraphic-Regular.woff",
        "MathJax_Fraktur-Bold.woff",
        "MathJax_Fraktur-Regular.woff",
        "MathJax_Main-Bold.woff",
        "MathJax_Main-Italic.woff",
        "MathJax_Main-Regular.woff",
        "MathJax_Math-BoldItalic.woff",
        "MathJax_Math-Italic.woff",
        "MathJax_SansSerif-Bold.woff",
        "MathJax_SansSerif-Italic.woff",
        "MathJax_SansSerif-Regular.woff",
        "MathJax_Script-Regular.woff",
        "MathJax_Size1-Regular.woff",
        "MathJax_Size2-Regular.woff",
        "MathJax_Size3-Regular.woff",
        "MathJax_Size4-Regular.woff",
        "MathJax_Typewriter-Regular.woff",
        "MathJax_Vector-Bold.woff",
        "MathJax_Vector-Regular.woff",
        "MathJax_Zero.woff",
    }

    missing = [font for font in sorted(expected_fonts) if not (font_dir / font).is_file()]

    assert missing == []
