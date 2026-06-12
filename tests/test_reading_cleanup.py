from pathlib import Path

from src.services.reading_cleanup import clean_reading_markdown


ACS_FIRST_PAGE_MARKDOWN = """
www.acsami.org

Research Article

# Dual-Layer Grain-Boundary In Situ Polymerization Modulates Elastic Modulus

Yeon-Woo Choi and Nam-Gyu Park

<div style="text-align: center;"><img src="assets/page_001/icon-orange.jpg" alt="Image" width="3%" /></div>

Cite This: https://doi.org/10.1021/acsami.6c05001

<div style="text-align: center;"><img src="assets/page_001/icon-blue.jpg" alt="Image" width="3%" /></div>

Read Online

ACCESS

Metrics & More

<div style="text-align: center;"><img src="assets/page_001/icon-metrics.jpg" alt="Image" width="2%" /></div>

Article Recommendations

<div style="text-align: center;"><img src="assets/page_001/icon-si.jpg" alt="Image" width="1%" /></div>

Supporting Information

ABSTRACT: Flexible all-perovskite tandem solar cells are promising. To address this intrinsic limitation, a dual-layer grain-boundary in situ polymer-

<div style="text-align: center;"><img src="assets/page_001/real-figure.jpg" alt="Image" width="18%" /></div>

ization strategy is introduced for both perovskite layers.

KEYWORDS: all perovskite tandem, flexible solar cell

### 1. INTRODUCTION

Perovskite solar cells have emerged as leading candidates.
"""


def test_clean_reading_markdown_removes_acs_navigation_icons_and_keeps_content_figures(tmp_path: Path) -> None:
    result = clean_reading_markdown(
        ACS_FIRST_PAGE_MARKDOWN,
        asset_root=tmp_path,
        page_number=1,
    )

    assert "Read Online" not in result.markdown
    assert "Metrics & More" not in result.markdown
    assert "Article Recommendations" not in result.markdown
    assert "Supporting Information\n\nABSTRACT" not in result.markdown
    assert "icon-orange.jpg" not in result.markdown
    assert "icon-blue.jpg" not in result.markdown
    assert "real-figure.jpg" in result.markdown
    assert "ABSTRACT: Flexible all-perovskite tandem solar cells" in result.markdown
    assert "KEYWORDS: all perovskite tandem" in result.markdown
    assert "polymerization strategy is introduced" in result.markdown
    assert result.report["removed_blocks"] >= 5
    assert result.report["removed_images"] >= 4


def test_clean_reading_markdown_removes_acs_advertising_blocks(tmp_path: Path) -> None:
    markdown = """
## REFERENCES

(1) A normal reference.

<div style="text-align: center;"><img src="assets/page_009/ad.jpg" alt="Image" width="10%" /></div>

CAS BIOFINDER DISCOVERY PLATFORM(TM)

ELIMINATE DATA

SILOS. FIND

WHAT YOU

NEED, WHEN

YOU NEED IT.

A single platform for relevant, high-quality biological and toxicology research

Streamline your R&D
"""

    result = clean_reading_markdown(markdown, asset_root=tmp_path, page_number=9)

    assert "A normal reference." in result.markdown
    assert "CAS BIOFINDER" not in result.markdown
    assert "ELIMINATE DATA" not in result.markdown
    assert "ad.jpg" not in result.markdown
    assert result.report["removed_blocks"] >= 2
