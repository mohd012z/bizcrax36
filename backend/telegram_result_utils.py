"""Pure helpers for stable menu pagination and idea deduplication."""
def deduplicate_ideas(ideas):
    unique={}
    for item in ideas:
        if not isinstance(item,dict):
            continue
        key=(str(item.get("title","")).strip().casefold(),
             str(item.get("country","Malaysia")).strip().casefold())
        if key[0] and key not in unique:
            unique[key]=item
    return list(unique.values())

def page(items, index=0, size=5):
    if size<1 or size>20:
        raise ValueError("invalid page size")
    count=len(items)
    pages=max(1,(count+size-1)//size)
    current=max(0,min(index,pages-1))
    return {"items":items[current*size:(current+1)*size],
            "page":current,"pages":pages,"total":count}
