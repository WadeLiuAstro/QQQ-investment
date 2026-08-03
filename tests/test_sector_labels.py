from pathlib import Path


def test_sector_cards_include_chinese_explanations() -> None:
    script = Path("static/assets/app.js").read_text(encoding="utf-8")

    for label in ["科技板块（XLK）", "半导体板块（SMH）", "能源板块（XLE）", "金融板块（XLF）"]:
        assert label in script
