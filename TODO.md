# Preflight Check Backlog

This is a working backlog of major checks still missing for book-publishing use cases.
It covers both print books and ebooks.

## Most Important Missing Checks

### Page Count and Page Sequence

- Expected page count
- Blank pages
- Odd/even page rules
- All pages same size or allowed size variation
- Cover vs interior page geometry

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

- PDF/X detection
- PDF/A detection
- PDF version policy
- OutputIntent profile details
- Metadata consistency

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

### Annotations and Interactive Content

Important for ebooks, usually unwanted for print.

- Links
- Forms
- JavaScript
- Embedded files
- Multimedia
- Annotations outside page boxes

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

1. Annotations, links, and embedded interactive content
2. Page sequence, page count, and blank pages
3. PDF/X, PDF version, and standards metadata
4. Cover-specific checks
5. Safe-area and bleed-content analysis
6. Deeper color checks such as TAC and rich black
