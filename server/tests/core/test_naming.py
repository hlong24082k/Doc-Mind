import unicodedata

from app.core.storage.naming import canonical_document_name as canon


def test_strips_directories_and_suffix():
    assert canon("../../etc/passwd.pdf") == "passwd"
    assert canon("..\\..\\x.PDF") == "x"


def test_nfd_and_nfc_are_equal():
    nfc = unicodedata.normalize("NFC", "Tài liệu.pdf")
    nfd = unicodedata.normalize("NFD", "Tài liệu.pdf")
    assert nfd != nfc
    assert canon(nfd) == canon(nfc) == "Tài liệu"


def test_forbidden_and_control_chars():
    assert canon("a:b*c?.pdf") == "a_b_c_"
    assert canon("a\x00b\nc.pdf") == "a_b_c"


def test_empty_names():
    for name in (".pdf", " . .pdf", "...pdf", "", None):
        assert canon(name) is None


def test_whitespace_collapsed():
    assert canon("  my    paper \t v2 .pdf") == "my paper _ v2"


def test_long_vietnamese_name_cut_on_char_boundary():
    name = canon("ệ" * 300 + ".pdf")
    assert name is not None
    raw = name.encode("utf-8")
    assert len(raw) <= 200
    assert raw.decode("utf-8") == name
    assert set(name) == {"ệ"}
