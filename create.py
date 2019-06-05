#!/usr/bin/env python3

SECTOR_SIZE = 2048

MAGIC = "MICROSOFT*XBOX*MEDIA".encode('ascii')

import os
import sys
import struct
import shutil

def padding(value, alignment):
  return (alignment - (value % alignment)) % alignment

def align_up(value, alignment):
  return value + padding(value, alignment)

def get_sector(offset):
  assert(offset % SECTOR_SIZE == 0)
  return offset // SECTOR_SIZE

def allocate_image(f, root_path):

  data_offset = 0

  def allocate_directory(root_path, path):
    nonlocal f    
    nonlocal data_offset

    offset = 0

    def allocate_file_entry(path, file_entries, index):
      nonlocal offset

      # Find the respective entry
      file_entry = file_entries[index]
      name = file_entry['name']

      # Calculate size for this entry
      file_entry_size = 0
      file_entry_size += 14
      file_entry_size += len(name)
      file_entry_size = align_up(file_entry_size, 4)

      # Fit entry in current sector or pad it
      offset_base = offset - (offset % SECTOR_SIZE)
      if ((offset + file_entry_size) >= (offset_base + SECTOR_SIZE)):
        offset = align_up(offset, SECTOR_SIZE)
        #FIXME: Untested.. need many long named files in single directory to trigger this
        assert(False)

      # Get the index of this entry
      assert(offset % 4 == 0)
      this_offset = offset // 4
      
      # Remember where this file entry should be
      file_entry['offset'] = this_offset

      # Allocate space for this entry
      offset += file_entry_size

      # Handle content
      usable_path = os.path.join(root_path, *path, name)
      if os.path.isdir(usable_path):

        # Allocate all subfolders
        dir_offset, dir_size = allocate_directory(root_path, path + [name]) 
        
        # Fixup directory information
        # Note that size is sector aligned for directories
        file_entry['size'] = align_up(dir_size, SECTOR_SIZE)
        file_entry['attrib'] |= 0x10
        file_entry['sector'] = get_sector(dir_offset)

      elif os.path.isfile(usable_path):

        #FIXME: Handle isfile / st_size and everything in one step
        statinfo = os.stat(usable_path)
        file_entry['size'] = statinfo.st_size

      else:
        print("Unknown file-entry-type: '%s'" % usable_path)
        assert(False)

      print("Reserved: %s [%u / %u]" % (path + [name], this_offset, offset))

      return this_offset

    def fixup_file_entry(path, file_entries, index, left, right):
      file_entry = file_entries[index]

      file_entry['left'] = left
      file_entry['right'] = right

      #print("Put ??? (0x%X) with 0x%X, 0x%X" % (offset, left, right))

    def allocate_file_entries(path, file_entries, left_inc, right_inc):

      # If there's less than one file, we can't allocate anything
      if (left_inc > right_inc):
        return 0x0000

      # Find the file in the middle of the directory
      middle = (left_inc + right_inc) // 2
      assert(middle >= left_inc)
      assert(middle <= right_inc)

      # Allocate one file from the middle of directory
      this_offset = allocate_file_entry(path, file_entries, middle)

      # Allocate other files in this directory
      left = allocate_file_entries(path, file_entries, left_inc, middle - 1)
      right = allocate_file_entries(path, file_entries, middle + 1, right_inc)

      # Fixup the now-known left/right nodes
      fixup_file_entry(path, file_entries, middle, left, right)

      return this_offset

    # Ask the host filesystem for a list of files
    usable_path = os.path.join(root_path, *path)
    files = os.listdir(usable_path)

    # We will construct a binary search tree; so we need a sorted list
    files.sort()

    # Collect all files for this directory
    file_entries = []
    for file in files:

      file_entry = {}
      file_entry['name'] = file
      file_entry['attrib'] = 0

      file_entries += [file_entry]

      print("Found %s" % file_entry)

    print("Handling '%s'/%s: %s" % (root_path, str(path), str(files)))
    allocate_file_entries(path, file_entries, 0, len(file_entries) - 1)

    # Now that all entries have been allocated, we know the directory size
    dir_size = offset

    # Emulate MS bug: empty directories should be size 0, but are size 2048
    if True:
      if dir_size == 0:
        dir_size = 1

    # Allocate space for directory entries
    dir_offset = data_offset
    allocated_dir_size = align_up(dir_size, SECTOR_SIZE)
    dir_buffer = bytearray([0xFF] * allocated_dir_size)
    data_offset += allocated_dir_size
    print("")
    print("Placing directory entry at 0x%X (sector %u), size: %d / %d" % (dir_offset, get_sector(dir_offset), dir_size, allocated_dir_size))

    # Do a second pass to place the data (done in reverse?)
    for file_entry in file_entries[::-1]:

      #FIXME: Handle pre-allocated sectors?

      # Retrieve some file data we'll often use
      name = file_entry['name']
      attrib = file_entry['attrib']
      offset = file_entry['offset'] * 4
      size = file_entry['size']

      # Wrie file contents
      if attrib & 0x10 == 0:
        print("Writing file")
        file_entry['sector'] = get_sector(data_offset)

        # Copy data from input to output
        usable_path = os.path.join(root_path, *path, name)
        with open(usable_path, 'rb') as fi:
          f.seek(data_offset)
          shutil.copyfileobj(fi, f, SECTOR_SIZE)

        # Advance cursor and ensure data alignment
        data_offset += size
        data_offset = align_up(data_offset, SECTOR_SIZE)

      print("Placed %s" % file_entry)

      # Write file_entry to buffer
      name_length = len(name)
      assert(name_length >= 1)
      struct.pack_into("<HHIIBB", dir_buffer, offset, file_entry['left'], file_entry['right'], file_entry['sector'], size, attrib, name_length)
      name_start = offset + 14
      name_end = name_start + name_length
      dir_buffer[name_start:name_end] = name.encode('ascii') # FIXME: lower 8 bit of UTF-16

    # Write directory entries to output
    f.seek(dir_offset)
    f.write(dir_buffer)

    return dir_offset, dir_size

  #FIXME: Add header; is this just padding?!
  f.seek(0x10000)
  data_offset += 0x10000

  # Write header
  f.write(MAGIC)
  data_offset += len(MAGIC)

  # Skip over root directory placeholder
  f.seek(8, os.SEEK_CUR) #FIXME: Skip
  data_offset += 8

  #FIXME: Write some timestamp
  f.write(bytes([0x00] * 8))
  data_offset += 8

  #FIXME: Write some padding
  f.write(bytes([0x00] * 0x7C8))
  data_offset += 0x7C8

  # Write footer
  f.write(MAGIC)
  data_offset += len(MAGIC)

  # Align to next sector
  data_offset = align_up(data_offset, SECTOR_SIZE)

  # Index the root directory
  root_offset, root_size = allocate_directory(root_path, [])
  print(hex(root_offset))
  print(root_size)

  # Fixup header
  f.seek(0x10000 + 20)
  print(MAGIC)
  root_sector = get_sector(root_offset)
  f.write(struct.pack("<II", root_sector, root_size))

  # Align image
  data_offset = align_up(data_offset, 0x10000) #FIXME: Is this the right alignment?
  #FIXME: Update file size

  print("Image is %u bytes" % data_offset)

  return# Return some image info?
