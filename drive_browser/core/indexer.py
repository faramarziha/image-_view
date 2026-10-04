"""
Indexer module:
- Builds hierarchical directory tree from flat list of entries
- Aggregates file counts and sizes (direct and recursive)
- Groups duplicates by (case-insensitive filename, exact size_kb)
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple
from core.models import FileEntry, FolderNode


def build_folder_tree(entries: List[FileEntry]) -> Tuple[Dict[str, FolderNode], Dict[str, FolderNode]]:
    """
    Constructs the folder hierarchy.
    Returns:
        roots: Mapping of drive paths (e.g. "E:\\") to top-level FolderNode
        flat_lookup: Mapping of all normalized folder paths to their FolderNode
    """
    roots: Dict[str, FolderNode] = {}
    flat_lookup: Dict[str, FolderNode] = {}

    for entry in entries:
        folder_path = entry.folder
        if not folder_path.endswith('\\'):
            folder_path += '\\'

        # If node already exists, increment its direct file info
        existing = flat_lookup.get(folder_path)
        if existing is not None:
            existing.direct_file_count += 1
            existing.direct_size_kb += entry.size_kb
            existing.file_indices.append(entry.index)
            continue

        # Split into path components e.g. "E:\pop\G\photo\" -> ["E:", "pop", "G", "photo"]
        clean_path = folder_path.replace('/', '\\')
        parts = [p for p in clean_path.split('\\') if p]
        if not parts:
            continue

        drive_key = parts[0] + '\\'
        if drive_key not in roots:
            root_node = FolderNode(name=parts[0], full_path=drive_key)
            roots[drive_key] = root_node
            flat_lookup[drive_key] = root_node

        current = roots[drive_key]
        accumulated_path = drive_key

        for part in parts[1:]:
            accumulated_path += part + '\\'
            node = flat_lookup.get(accumulated_path)
            if node is None:
                node = current.get_or_create_child(part, accumulated_path)
                flat_lookup[accumulated_path] = node
            current = node

        current.direct_file_count += 1
        current.direct_size_kb += entry.size_kb
        current.file_indices.append(entry.index)

    # Compute bottom-up recursive totals
    for root in roots.values():
        root.compute_recursive_totals()

    return roots, flat_lookup


def build_duplicate_index(entries: List[FileEntry]) -> Dict[Tuple[str, float], List[int]]:
    """
    Index identical files by (lowercase name, size_kb).
    Returns only entries having 2 or more files.
    """
    groups: Dict[Tuple[str, float], List[int]] = defaultdict(list)
    for entry in entries:
        key = (entry.name.lower(), entry.size_kb)
        groups[key].append(entry.index)

    return {k: v for k, v in groups.items() if len(v) >= 2}


def extract_unique_extensions(entries: List[FileEntry]) -> List[str]:
    """Return sorted unique extensions."""
    unique = {e.extension for e in entries if e.extension}
    return sorted(unique)


def extract_unique_categories(entries: List[FileEntry]) -> List[str]:
    """Return sorted unique categories."""
    unique = {e.category for e in entries if e.category}
    return sorted(unique)
