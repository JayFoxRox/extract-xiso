#!/usr/bin/env python3

import os
import sys
import struct

SECTOR_SIZE = 2048

XISO_HEADER_DATA_LENGTH = 20
XISO_HEADER_OFFSET = 0x10000

def extract_file(f, root_path, path, data_offset, size, attrib):
  print("// %s" % str(path))

  usable_path = os.path.join(root_path, *path)
  with open(usable_path, 'wb') as fo:
    f.seek(data_offset)
    while size > 0:
      buffer = f.read(min(size, SECTOR_SIZE))
      fo.write(buffer)
      size -= len(buffer)

def extract_search_tree(f, root_path, dir_path, dir_offset, dir_size, offset):

  assert(offset != 0xFFFF)

  this_offset = dir_offset + offset * 4

  # Error if offset is outside directory
  if (offset * 4) >= dir_size:
    print("_0x%X [label=\"(out-of-bounds)\\n0x%X\", shape=octagon, style=filled, fillcolor=lightcoral]" % (this_offset, this_offset))
    return

  #print("// offset %u / %u" % (offset * 4, dir_size))

  f.seek(dir_offset + offset * 4)
  left, right, sector, size, attrib, name_length = struct.unpack("<HHIIBB", f.read(14))
  data_offset = sector * SECTOR_SIZE
  offset += 14

  # MS kernel checks for empty directory is directory size = 0.
  # However, their tools set directory size to 2048 and 0xFF-fill the sector.
  # Their directory-listing detects 0xFFFF L/R index as "go to end of sector".
  # Their file-search isn't aware. So for empty directories, it sees garbage.
  #
  # 1. Searching in empty directory fails with STATUS_DISK_CORRUPT_ERROR.
  # 2. Empty directories have file: "\xFF" * 0xFF; but filtered by bound-check.
  #    Sector bound-check will lead to STATUS_DISK_CORRUPT_ERROR.
  # 3. Listing empty directory works with STATUS_END_OF_FILE.
  #    No files will be found.
  #
  # This is a work-around for 1 and 2.
  #
  # We simply abort loading directories for L/R index 0xFFFF.
  # This shouldn't happen during normal search: L/R index just skip sector pad.
  if True:
    if left == 0xFFFF:
      assert(right == 0xFFFF)

      print("_0x%X [label=\"(sector-pad)\\n0x%X\", shape=invhouse, style=filled, fillcolor=lightcoral]" % (this_offset, this_offset))

      return
    else:
      assert(right != 0xFFFF)

  # Parse filname
  name = f.read(name_length)
  name = name.decode('ascii') #FIXME: Actually first 0xFF of UTF-16 (?)
  pad = (4 - (name_length % 4)) % 4
  f.read(pad)

  # Construct path but filter dangerous symbols (security)
  #FIXME: For security reasons, disallow certain symbols: '..', '/', '\\' ?
  path = dir_path + [name]

  # Create node for file entry
  #FIXME: Choose colors for different layers?
  print("_0x%X [label=\"(0x%X)\\n\\'%s\\'\\ndata: 0x%X\\nsize: %u\\n0x%X\\n(0x%X | 0x%X)\", shape=%s]" % (this_offset, (this_offset - dir_offset) // 4, str(name), data_offset, size, this_offset, left, right, "folder, style=filled, fillcolor=khaki1" if (attrib & 0x10) else "note"))
  link_color = "black" #FIXME: "red" if (child_data_offset < data_offset) else "green"

  # Handle left children (or lack thereof)
  if left != 0:
    print("_0x%X -> _0x%X [tailport=w, headport=n, color=%s]" % (this_offset, dir_offset + left * 4, link_color))
    extract_search_tree(f, root_path, dir_path, dir_offset, dir_size, left)
  else:
    print("_0x%X_l [shape=point]" % (this_offset))
    print("_0x%X -> _0x%X_l [tailport=w, headport=n]" % (this_offset, this_offset))

  # Handle element
  if attrib & 0x10:

    # Create the folder
    usable_path = os.path.join(root_path, *path)
    try:
      os.mkdir(usable_path)
    except FileExistsError:
      print("Warning: '%s' exists already" % usable_path, file=sys.stderr)

    # Never happens with MS images, because of a bug in their XISO generator
    # Still checked in kernel though (see note above)
    if size == 0:
      print("_0x%X [fillcolor=lightgray]" % this_offset)
    else:
      print("_0x%X -> _0x%X [tailport=s, headport=n, style=dashed, minlen=3.0]" % (this_offset, data_offset))
      extract_search_tree(f, root_path, path, data_offset, size, 0)

  else:
    extract_file(f, root_path, path, data_offset, size, attrib)

  # Handle right children (or lack thereof)
  if right != 0:
    print("_0x%X -> _0x%X [tailport=e, headport=n, color=%s]" % (this_offset, dir_offset + right * 4, link_color))
    extract_search_tree(f, root_path, dir_path, dir_offset, dir_size, right)
  else:
    print("_0x%X_r [shape=point]" % (this_offset))
    print("_0x%X -> _0x%X_r [tailport=e, headport=n]" % (this_offset, this_offset))


def extract_image(f, root_path):
  print("digraph G {")
  f.seek(XISO_HEADER_OFFSET)
  magic = f.read(XISO_HEADER_DATA_LENGTH)
  print("// magic: '%s'" % magic)
  root_sector, root_size = struct.unpack("<II", f.read(8))
  root_offset = root_sector * SECTOR_SIZE
  print("root [label=\"root\\ndata: 0x%X\\nsize: %u\"]" % (root_offset, root_size))
  print("root -> _0x%X" % (root_offset))
  extract_search_tree(f, root_path, [], root_offset, root_size, 0)
  print("}")
