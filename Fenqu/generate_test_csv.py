#!/usr/bin/env python
"""Generate test CSV file with 150 sample user records."""
import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Fenqu.settings')
django.setup()

from segmentation.utils import generate_sample_data

if __name__ == '__main__':
    # Generate 150 records
    buffer = generate_sample_data(num_rows=150)
    
    # Save to test.csv in Fenqu root directory
    output_path = os.path.join(os.path.dirname(__file__), 'test.csv')
    with open(output_path, 'wb') as f:
        f.write(buffer.read())
    
    print(f"Successfully generated test.csv with 150 records at: {output_path}")

