#!/usr/bin/env python3

import extract
import create

import sys

if __name__ == "__main__":
  print("extract-xiso")

  option = sys.argv[1]

  # Extract XISO
  if option == "-x":
    image_path = sys.argv[2]
    root_path = sys.argv[3]
    with open(image_path, 'rb') as f:
      extract.extract_image(f, root_path)

  # Create XISO
  elif option == "-c":
    root_path = sys.argv[2]
    image_path = sys.argv[3]
    with open(image_path, 'wb') as f:
      create.allocate_image(f, root_path)

  else:
    print("Unknown option")
