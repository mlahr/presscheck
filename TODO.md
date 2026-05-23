# Preflight Check Backlog

This is a working backlog of major checks still missing for book-publishing use cases.
It covers both print books and ebooks.

## Most Important Missing Checks

## Implemented From This Backlog

### Annotations and Interactive Content

Implemented:

- Links
- Forms
- JavaScript
- Embedded files
- Annotations outside page boxes

Still missing:

- Multimedia-specific detection beyond annotation subtype/action evidence

### Page Count and Page Sequence

Implemented:

- Expected page count
- Blank pages
- Odd/even page rules
- All pages same size or allowed size variation

Still missing:

- Cover vs interior page geometry

### PDF Standards and Conformance Intent

Implemented:

- PDF/X detection from declared XMP metadata
- PDF/A detection from declared XMP metadata
- PDF version policy
- Producer/creator metadata policy

Still missing:

- OutputIntent profile details
- Deeper metadata consistency

## Remaining Major Missing Checks

### Bleed Content Quality

Current checks validate page boxes and object bounds, but not whether bleed is actually filled.

- White or empty bleed zones
- Content stopping exactly at trim
- Important content too close to trim or safe area

### Text Safety

- Text too close to trim or spine
- Invisible text
- Text rendered as image
- Outlined text detection
- Black text not pure K in print targets
- Overprint behavior specifically for black text

### Cover-Specific Checks

These are critical for print books.

- Cover spread dimensions
- Spine width
- Front, back, and flap areas
- Barcode area present and clear
- Cover-specific trim and bleed rules

### PDF Standards and Conformance Intent

- OutputIntent profile details
- Deeper metadata consistency

### Deeper Color Checks

Current checks cover basic color spaces, spot colors, registration color, and overprint.
Still missing:

- Rich black detection
- Total ink coverage / TAC
- Small black text in RGB or rich black
- Grayscale image policy
- Spot color alternate-space sanity

### Image Quality

Current checks cover resolution, filters, JPEG/DCT compression, color spaces, and soft masks.
Still missing:

- Upscaled images beyond threshold
- 1-bit image resolution rules
- Suspiciously tiny image dimensions
- Alpha/transparency in images for print
- JPEG artifact heuristics, later and optional

### Bookmarks and Navigation

Important for ebooks.

- Outline/bookmarks present
- Links valid
- Internal destinations valid
- Table-of-contents link coverage

### Accessibility and Structure

Mostly ebook-focused.

- Tagged PDF
- Document language
- Alt text for images
- Reading order
- Title metadata

## Suggested Priority

1. Cover-specific checks
2. Safe-area and bleed-content analysis
3. Deeper color checks such as TAC and rich black
4. OutputIntent profile details and deeper metadata consistency
