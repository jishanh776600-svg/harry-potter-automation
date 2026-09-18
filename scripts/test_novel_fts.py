import sys
sys.path.insert(0, ".")
from engines.novel_knowledge_engine import NovelKnowledgeEngine

eng = NovelKnowledgeEngine()

tests = [
    ("Mirror Erised desire", None),
    ("Quirrell Voldemort forest", None),
    ("Patronus doe silver Snape", None),
    ("Dumbledore Dursleys protection", None),
    ("Hermione research library", None),
    ("Peeves poltergeist ghost", None),
    ("Neville sorting hat Hufflepuff", None),
    ("Dobby house elf bound", None),
    ("always Snape doe patronus", 7),
    ("Mirror heart desire show", 1),
    ("protection blood ancient magic Lily", None),
]

print("=" * 80)
print("NOVEL FTS SEARCH DIAGNOSTIC")
print("=" * 80)
for q, b in tests:
    try:
        res = eng.search(q, book_number=b, limit=1)
        if res:
            r = res[0]
            text_preview = r["text"][:150].replace("\n", " ").encode("ascii", "replace").decode("ascii")
            print(f"FOUND   [{q}]: B{r['book_number']} C{r['chapter_number']} {r['chapter_title']}")
            print(f"         Preview: {text_preview}")
        else:
            print(f"NONE    [{q}] (book={b})")
    except Exception as e:
        print(f"ERROR   [{q}]: {e}")
    print()
