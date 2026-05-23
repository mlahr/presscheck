package com.pdfdancer.preflight.pdfbox;

import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDFormContentStream;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.PDResources;
import org.apache.pdfbox.pdmodel.PDDocumentNameDictionary;
import org.apache.pdfbox.pdmodel.PDEmbeddedFilesNameTreeNode;
import org.apache.pdfbox.pdmodel.PDDocumentInformation;
import org.apache.pdfbox.pdmodel.common.PDMetadata;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.common.filespecification.PDComplexFileSpecification;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.apache.pdfbox.cos.COSArray;
import org.apache.pdfbox.cos.COSDictionary;
import org.apache.pdfbox.cos.COSFloat;
import org.apache.pdfbox.cos.COSInteger;
import org.apache.pdfbox.cos.COSName;
import org.apache.pdfbox.pdmodel.graphics.blend.BlendMode;
import org.apache.pdfbox.pdmodel.graphics.color.PDColor;
import org.apache.pdfbox.pdmodel.graphics.color.PDSeparation;
import org.apache.pdfbox.pdmodel.graphics.color.PDOutputIntent;
import org.apache.pdfbox.pdmodel.graphics.form.PDFormXObject;
import org.apache.pdfbox.pdmodel.graphics.state.PDExtendedGraphicsState;
import org.apache.pdfbox.pdmodel.graphics.image.JPEGFactory;
import org.apache.pdfbox.pdmodel.graphics.image.LosslessFactory;
import org.apache.pdfbox.pdmodel.graphics.image.PDImageXObject;
import org.apache.pdfbox.pdmodel.interactive.action.PDActionJavaScript;
import org.apache.pdfbox.pdmodel.interactive.action.PDActionURI;
import org.apache.pdfbox.pdmodel.interactive.annotation.PDAnnotationLink;
import org.apache.pdfbox.pdmodel.interactive.form.PDAcroForm;
import org.apache.pdfbox.pdmodel.interactive.form.PDTextField;
import org.apache.pdfbox.util.Matrix;
import org.apache.xmpbox.XMPMetadata;
import org.apache.xmpbox.schema.PDFAIdentificationSchema;
import org.apache.xmpbox.xml.XmpSerializer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.awt.Color;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class PdfBoxAnalyzerTest {
    @TempDir
    Path tempDir;

    @Test
    void reportsNonEmbeddedStandardFont() throws Exception {
        File pdf = tempDir.resolve("standard-font.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.beginText();
                content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                content.newLineAtOffset(72, 720);
                content.showText("Hello");
                content.endText();
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        assertEquals(true, result.get("ok"));
        assertEquals(Map.of("page_count", 1), result.get("metadata"));

        Map<String, Object> evidence = firstEvidenceFor(result, "fonts.non_embedded");
        assertEquals("fonts", evidence.get("category"));
        assertEquals(1, evidence.get("page"));
        assertEquals(false, evidence.get("embedded"));
    }

    @Test
    void reportsTextSizeEvidence() throws Exception {
        File pdf = tempDir.resolve("text-size.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.beginText();
                content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                content.newLineAtOffset(72, 720);
                content.showText("Hi");
                content.endText();
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "fonts.text_size");
        assertEquals("fonts", evidence.get("category"));
        assertEquals(1, evidence.get("page"));
        assertEquals("Helvetica", evidence.get("font_name"));
        assertEquals("Type1", evidence.get("subtype"));
        assertDoubleEquals(12.0, evidence.get("effective_size_pt"));
        assertDoubleEquals(12.0, evidence.get("horizontal_size_pt"));
        assertEquals(2, evidence.get("occurrences"));

        Map<String, Object> boundsEvidence = firstEvidenceFor(result, "geometry.text_bounds");
        assertEquals("geometry", boundsEvidence.get("category"));
        assertEquals(1, boundsEvidence.get("page"));
        assertEquals("text", boundsEvidence.get("object_type"));
        assertEquals("Helvetica", boundsEvidence.get("font_name"));
        assertDoubleEquals(12.0, boundsEvidence.get("effective_size_pt"));
        assertBounds(boundsEvidence, 72.0, 717.3, 83.328, 731.172);
    }

    @Test
    void reportsScaledTextEffectiveSize() throws Exception {
        File pdf = tempDir.resolve("scaled-text-size.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.saveGraphicsState();
                content.transform(new Matrix(0.5f, 0, 0, 0.5f, 0, 0));
                content.beginText();
                content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                content.newLineAtOffset(72, 720);
                content.showText("Hi");
                content.endText();
                content.restoreGraphicsState();
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "fonts.text_size");
        assertDoubleEquals(6.0, evidence.get("effective_size_pt"));
        assertDoubleEquals(6.0, evidence.get("horizontal_size_pt"));
    }

    @Test
    void reportsTextSizeInsideFormXObject() throws Exception {
        File pdf = tempDir.resolve("form-text-size.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);

            PDFormXObject form = new PDFormXObject(document);
            form.setResources(new PDResources());
            form.setBBox(new PDRectangle(100, 100));
            try (PDFormContentStream content = new PDFormContentStream(form)) {
                content.beginText();
                content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 8);
                content.newLineAtOffset(10, 80);
                content.showText("Hi");
                content.endText();
            }

            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.drawForm(form);
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "fonts.text_size");
        assertEquals("Form1", evidence.get("resource_path"));
        assertDoubleEquals(8.0, evidence.get("effective_size_pt"));
        assertEquals(2, evidence.get("occurrences"));

        Map<String, Object> boundsEvidence = firstEvidenceFor(result, "geometry.text_bounds", "Form1");
        assertEquals("text", boundsEvidence.get("object_type"));
        assertEquals("Form1", boundsEvidence.get("resource_path"));
        assertDoubleEquals(8.0, boundsEvidence.get("effective_size_pt"));
    }

    @Test
    void reportsMissingOutputIntent() throws Exception {
        File pdf = tempDir.resolve("no-output-intent.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "color.output_intents");
        assertEquals("color", evidence.get("category"));
        assertEquals("document", evidence.get("scope"));
        assertEquals(0, evidence.get("count"));
        assertEquals(List.of(), evidence.get("output_intents"));
    }

    @Test
    void reportsPresentOutputIntent() throws Exception {
        File pdf = tempDir.resolve("with-output-intent.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            PDOutputIntent outputIntent = new PDOutputIntent(document, new ByteArrayInputStream(minimalRgbIccProfile()));
            outputIntent.setInfo("sRGB IEC61966-2.1");
            outputIntent.setOutputCondition("sRGB IEC61966-2.1");
            outputIntent.setOutputConditionIdentifier("sRGB IEC61966-2.1");
            outputIntent.setRegistryName("http://www.color.org");
            document.getDocumentCatalog().addOutputIntent(outputIntent);
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "color.output_intents");
        assertEquals(1, evidence.get("count"));

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> outputIntents = (List<Map<String, Object>>) evidence.get("output_intents");
        assertEquals("sRGB IEC61966-2.1", outputIntents.get(0).get("output_condition_identifier"));
        assertEquals("http://www.color.org", outputIntents.get(0).get("registry_name"));
        assertEquals(true, outputIntents.get(0).get("has_dest_output_profile"));
    }

    @Test
    void reportsPdfVersionEvidence() throws Exception {
        File pdf = tempDir.resolve("pdf-version.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            document.setVersion(1.7f);
            document.getDocumentCatalog().setVersion("2.0");
            document.addPage(new PDPage());
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "document_metadata.pdf_version");
        assertEquals("document_metadata", evidence.get("category"));
        assertEquals("document", evidence.get("scope"));
        assertEquals("2.0", evidence.get("document_version"));
        assertEquals("2.0", evidence.get("catalog_version"));
        assertEquals("2.0", evidence.get("effective_version"));
    }

    @Test
    void reportsDocumentInfoEvidence() throws Exception {
        File pdf = tempDir.resolve("document-info.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            PDDocumentInformation info = new PDDocumentInformation();
            info.setTitle("Book Title");
            info.setAuthor("Author Name");
            info.setCreator("Layout App");
            info.setProducer("PDF Producer");
            document.setDocumentInformation(info);
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "document_metadata.info");
        assertEquals("Book Title", evidence.get("title"));
        assertEquals("Author Name", evidence.get("author"));
        assertEquals("Layout App", evidence.get("creator"));
        assertEquals("PDF Producer", evidence.get("producer"));
    }

    @Test
    void reportsPdfaXmpEvidence() throws Exception {
        File pdf = tempDir.resolve("pdfa-xmp.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            XMPMetadata xmp = XMPMetadata.createXMPMetadata();
            PDFAIdentificationSchema pdfa = xmp.createAndAddPDFAIdentificationSchema();
            pdfa.setPart(2);
            pdfa.setConformance("B");
            PDMetadata metadata = new PDMetadata(document);
            metadata.importXMPMetadata(serializeXmp(xmp));
            document.getDocumentCatalog().setMetadata(metadata);
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "document_metadata.xmp_standards");
        assertEquals(true, evidence.get("has_xmp"));
        assertEquals(true, evidence.get("xmp_parseable"));
        assertEquals(2, evidence.get("pdfa_part"));
        assertEquals("B", evidence.get("pdfa_conformance"));
    }

    @Test
    void reportsPdfxXmpEvidence() throws Exception {
        File pdf = tempDir.resolve("pdfx-xmp.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            PDMetadata metadata = new PDMetadata(document);
            metadata.importXMPMetadata(pdfxXmp().getBytes(StandardCharsets.UTF_8));
            document.getDocumentCatalog().setMetadata(metadata);
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "document_metadata.xmp_standards");
        assertEquals(true, evidence.get("has_xmp"));
        assertEquals(true, evidence.get("xmp_parseable"));
        assertEquals("PDF/X-4", evidence.get("pdfx_version"));
        assertEquals("PDF/X-4", evidence.get("pdfx_conformance"));
    }

    @Test
    void reportsMalformedXmpEvidence() throws Exception {
        File pdf = tempDir.resolve("malformed-xmp.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            PDMetadata metadata = new PDMetadata(document);
            metadata.importXMPMetadata("<x:xmpmeta>".getBytes(StandardCharsets.UTF_8));
            document.getDocumentCatalog().setMetadata(metadata);
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "document_metadata.xmp_standards");
        assertEquals(true, evidence.get("has_xmp"));
        assertEquals(false, evidence.get("xmp_parseable"));
        assertEquals("XmpParsingException", evidence.get("parse_error_type"));
    }

    @Test
    void reportsBlankPageContentEvidence() throws Exception {
        File pdf = tempDir.resolve("blank-page.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "pages.page_content");
        assertEquals("pages", evidence.get("category"));
        assertEquals(1, evidence.get("page"));
        assertEquals(false, evidence.get("has_content_stream"));
        assertEquals(0, evidence.get("text_glyph_count"));
        assertEquals(0, evidence.get("image_count"));
        assertEquals(0, evidence.get("painted_path_count"));
        assertEquals(0, evidence.get("shading_count"));
        assertEquals(0, evidence.get("form_xobject_count"));
        assertEquals(true, evidence.get("is_structurally_blank"));
    }

    @Test
    void reportsTextPageAsNonblank() throws Exception {
        File pdf = tempDir.resolve("text-page.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.beginText();
                content.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 12);
                content.newLineAtOffset(72, 720);
                content.showText("Hi");
                content.endText();
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "pages.page_content");
        assertEquals(true, evidence.get("has_content_stream"));
        assertEquals(2, evidence.get("text_glyph_count"));
        assertEquals(false, evidence.get("is_structurally_blank"));
    }

    @Test
    void reportsPaintedPathPageAsNonblank() throws Exception {
        File pdf = tempDir.resolve("painted-path-page.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.addRect(72, 500, 100, 100);
                content.fill();
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "pages.page_content");
        assertEquals(1, evidence.get("painted_path_count"));
        assertEquals(false, evidence.get("is_structurally_blank"));
    }

    @Test
    void reportsImageEffectiveResolutionAtOneHundredDpi() throws Exception {
        File pdf = writeImagePdf("image-100dpi.pdf", 300, 300, 216, 216);

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "images.effective_resolution");
        assertEquals("images", evidence.get("category"));
        assertEquals(1, evidence.get("page"));
        assertEquals(300, evidence.get("pixel_width"));
        assertEquals(300, evidence.get("pixel_height"));
        assertDoubleEquals(216.0, evidence.get("drawn_width_pt"));
        assertDoubleEquals(216.0, evidence.get("drawn_height_pt"));
        assertDoubleEquals(100.0, evidence.get("x_dpi"));
        assertDoubleEquals(100.0, evidence.get("y_dpi"));
        assertDoubleEquals(100.0, evidence.get("min_dpi"));
        assertEquals("DeviceRGB", evidence.get("color_space_name"));
        assertEquals("DeviceRGB", evidence.get("color_space_family"));
        assertEquals(List.of("FlateDecode"), evidence.get("filters"));
        assertEquals(8, evidence.get("bits_per_component"));
        assertEquals(false, evidence.get("interpolate"));
        assertEquals(false, evidence.get("image_mask"));
        assertEquals(false, evidence.get("has_soft_mask"));
        assertEquals(false, evidence.get("has_explicit_mask"));

        Map<String, Object> boundsEvidence = firstEvidenceFor(result, "geometry.object_bounds");
        assertEquals("geometry", boundsEvidence.get("category"));
        assertEquals("image", boundsEvidence.get("object_type"));
        assertEquals("Im1", boundsEvidence.get("resource_path"));
        assertBounds(boundsEvidence, 72.0, 500.0, 288.0, 716.0);

        Map<String, Object> pageContent = firstEvidenceFor(result, "pages.page_content");
        assertEquals(1, pageContent.get("image_count"));
        assertEquals(false, pageContent.get("is_structurally_blank"));
    }

    @Test
    void reportsImageEffectiveResolutionAtThreeHundredDpi() throws Exception {
        File pdf = writeImagePdf("image-300dpi.pdf", 300, 300, 72, 72);

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "images.effective_resolution");
        assertDoubleEquals(300.0, evidence.get("x_dpi"));
        assertDoubleEquals(300.0, evidence.get("y_dpi"));
        assertDoubleEquals(300.0, evidence.get("min_dpi"));
    }

    @Test
    void reportsJpegImageFilter() throws Exception {
        File pdf = tempDir.resolve("jpeg-image.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            PDImageXObject image = createJpegImage(document, 300, 300);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.drawImage(image, 72, 500, 72, 72);
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "images.effective_resolution");
        assertEquals(List.of("DCTDecode"), evidence.get("filters"));
    }

    @Test
    void reportsImageSoftMask() throws Exception {
        File pdf = tempDir.resolve("soft-mask-image.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            PDImageXObject image = createBlueImage(document, 300, 300);
            PDImageXObject mask = createGrayImage(document, 300, 300);
            image.getCOSObject().setItem(COSName.SMASK, mask);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.drawImage(image, 72, 500, 72, 72);
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "images.effective_resolution");
        assertEquals(true, evidence.get("has_soft_mask"));
    }

    @Test
    void reportsImageEffectiveResolutionInsideFormXObject() throws Exception {
        File pdf = tempDir.resolve("form-image.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);

            PDFormXObject form = new PDFormXObject(document);
            form.setResources(new PDResources());
            form.setBBox(new PDRectangle(1, 1));
            PDImageXObject image = createBlueImage(document, 300, 300);
            try (PDFormContentStream content = new PDFormContentStream(form)) {
                content.drawImage(image, 0, 0, 1, 1);
            }

            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.saveGraphicsState();
                content.transform(new Matrix(216, 0, 0, 216, 72, 500));
                content.drawForm(form);
                content.restoreGraphicsState();
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "images.effective_resolution");
        assertEquals("Im1", evidence.get("resource_name"));
        assertEquals("Form1/Im1", evidence.get("resource_path"));
        assertDoubleEquals(216.0, evidence.get("drawn_width_pt"));
        assertDoubleEquals(216.0, evidence.get("drawn_height_pt"));
        assertDoubleEquals(100.0, evidence.get("min_dpi"));

        Map<String, Object> formBounds = firstEvidenceFor(result, "geometry.object_bounds", "Form1");
        assertEquals("form", formBounds.get("object_type"));
        assertBounds(formBounds, 72.0, 500.0, 288.0, 716.0);

        Map<String, Object> imageBounds = firstEvidenceFor(result, "geometry.object_bounds", "Form1/Im1");
        assertEquals("image", imageBounds.get("object_type"));
        assertBounds(imageBounds, 72.0, 500.0, 288.0, 716.0);

        Map<String, Object> pageContent = firstEvidenceFor(result, "pages.page_content");
        assertEquals(1, pageContent.get("form_xobject_count"));
        assertEquals(1, pageContent.get("image_count"));
        assertEquals(false, pageContent.get("is_structurally_blank"));
    }

    @Test
    void reportsTransparencyInsideFormXObject() throws Exception {
        File pdf = tempDir.resolve("form-transparency.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);

            PDFormXObject form = new PDFormXObject(document);
            form.setResources(new PDResources());
            form.setBBox(new PDRectangle(100, 100));
            PDExtendedGraphicsState graphicsState = new PDExtendedGraphicsState();
            graphicsState.setNonStrokingAlphaConstant(0.5f);
            try (PDFormContentStream content = new PDFormContentStream(form)) {
                content.setGraphicsStateParameters(graphicsState);
                content.addRect(0, 0, 100, 100);
                content.fill();
            }

            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.drawForm(form);
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "transparency.features");
        assertEquals("gs1", evidence.get("resource_name"));
        assertEquals("Form1/gs1", evidence.get("resource_path"));
        assertEquals(List.of("non_stroking_alpha"), evidence.get("features"));
    }

    @Test
    void ignoresUnusedImageResourceInsideFormXObject() throws Exception {
        File pdf = tempDir.resolve("form-unused-image.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);

            PDFormXObject form = new PDFormXObject(document);
            form.setResources(new PDResources());
            form.setBBox(new PDRectangle(100, 100));
            form.getResources().add(createBlueImage(document, 300, 300));
            try (PDFormContentStream content = new PDFormContentStream(form)) {
                content.addRect(0, 0, 100, 100);
                content.fill();
            }

            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.drawForm(form);
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        assertFalse(hasEvidenceFor(result, "images.effective_resolution"));
    }

    @Test
    void reportsAppliedNonStrokingAlpha() throws Exception {
        File pdf = tempDir.resolve("transparent-fill.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);

            PDExtendedGraphicsState graphicsState = new PDExtendedGraphicsState();
            graphicsState.setNonStrokingAlphaConstant(0.5f);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.setGraphicsStateParameters(graphicsState);
                content.addRect(72, 500, 100, 100);
                content.fill();
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "transparency.features");
        assertEquals("transparency", evidence.get("category"));
        assertEquals(1, evidence.get("page"));
        assertEquals(List.of("non_stroking_alpha"), evidence.get("features"));
        assertDoubleEquals(0.5, evidence.get("non_stroking_alpha"));
    }

    @Test
    void reportsAppliedBlendMode() throws Exception {
        File pdf = tempDir.resolve("multiply-blend.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);

            PDExtendedGraphicsState graphicsState = new PDExtendedGraphicsState();
            graphicsState.setBlendMode(BlendMode.MULTIPLY);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.setGraphicsStateParameters(graphicsState);
                content.addRect(72, 500, 100, 100);
                content.fill();
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "transparency.features");
        assertEquals(List.of("blend_mode"), evidence.get("features"));
        assertEquals("Multiply", evidence.get("blend_mode"));
    }

    @Test
    void reportsRegistrationColorUsage() throws Exception {
        File pdf = tempDir.resolve("registration-color.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            page.setResources(new PDResources());
            page.getResources().put(COSName.getPDFName("CS1"), separationColorSpace("All"));
            document.addPage(page);

            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.setNonStrokingColor(new PDColor(new float[]{1.0f}, separationColorSpace("All")));
                content.addRect(72, 500, 100, 100);
                content.fill();
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "color.special_color_usage");
        assertEquals("color", evidence.get("category"));
        assertEquals(1, evidence.get("page"));
        assertEquals("path_fill", evidence.get("paint_operation"));
        assertEquals("non_stroking", evidence.get("paint_role"));
        assertEquals("Separation", evidence.get("color_space_family"));
        assertEquals(List.of("All"), evidence.get("colorants"));
        assertEquals(1, evidence.get("occurrences"));
    }

    @Test
    void reportsSpotColorUsageInsideFormXObject() throws Exception {
        File pdf = tempDir.resolve("form-spot-color.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);

            PDFormXObject form = new PDFormXObject(document);
            form.setResources(new PDResources());
            form.getResources().put(COSName.getPDFName("CS1"), separationColorSpace("SpotGreen"));
            form.setBBox(new PDRectangle(100, 100));
            try (PDFormContentStream content = new PDFormContentStream(form)) {
                content.setNonStrokingColor(new PDColor(new float[]{0.5f}, separationColorSpace("SpotGreen")));
                content.addRect(0, 0, 100, 100);
                content.fill();
            }

            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.drawForm(form);
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "color.special_color_usage");
        assertEquals("Form1", evidence.get("resource_path"));
        assertEquals(List.of("SpotGreen"), evidence.get("colorants"));
    }

    @Test
    void reportsAppliedOverprint() throws Exception {
        File pdf = tempDir.resolve("overprint.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);

            PDExtendedGraphicsState graphicsState = new PDExtendedGraphicsState();
            graphicsState.setNonStrokingOverprintControl(true);
            graphicsState.setOverprintMode(1);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.setGraphicsStateParameters(graphicsState);
                content.addRect(72, 500, 100, 100);
                content.fill();
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "graphics.overprint_usage");
        assertEquals("graphics", evidence.get("category"));
        assertEquals(1, evidence.get("page"));
        assertEquals("path_fill", evidence.get("paint_operation"));
        assertEquals("non_stroking", evidence.get("paint_role"));
        assertEquals(1, evidence.get("overprint_mode"));
        assertEquals(1, evidence.get("occurrences"));
    }

    @Test
    void reportsLinkAnnotationWithUriAndBounds() throws Exception {
        File pdf = tempDir.resolve("link-annotation.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            page.setCropBox(new PDRectangle(0, 0, 200, 200));
            document.addPage(page);

            PDAnnotationLink link = new PDAnnotationLink();
            link.setRectangle(new PDRectangle(10, 10, 50, 20));
            link.setPrinted(true);
            PDActionURI action = new PDActionURI();
            action.setURI("https://example.com");
            link.setAction(action);
            page.setAnnotations(List.of(link));
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "interactive.annotations");
        assertEquals("interactive", evidence.get("category"));
        assertEquals(1, evidence.get("page"));
        assertEquals("Link", evidence.get("subtype"));
        assertEquals(true, evidence.get("printed"));
        assertEquals(false, evidence.get("outside_crop_box"));
        assertEquals("URI", evidence.get("action_subtype"));
        assertEquals("https://example.com", evidence.get("uri"));
    }

    @Test
    void reportsAnnotationOutsideCropBox() throws Exception {
        File pdf = tempDir.resolve("outside-annotation.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            page.setCropBox(new PDRectangle(0, 0, 200, 200));
            document.addPage(page);

            PDAnnotationLink link = new PDAnnotationLink();
            link.setRectangle(new PDRectangle(190, 10, 40, 20));
            page.setAnnotations(List.of(link));
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "interactive.annotations");
        assertEquals(true, evidence.get("outside_crop_box"));
    }

    @Test
    void reportsJavaScriptOpenAction() throws Exception {
        File pdf = tempDir.resolve("javascript-open-action.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            document.getDocumentCatalog().setOpenAction(new PDActionJavaScript("app.alert('x')"));
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "interactive.document_actions");
        assertEquals("document", evidence.get("scope"));
        assertEquals("OpenAction", evidence.get("location"));
        assertEquals("JavaScript", evidence.get("action_subtype"));
        assertEquals(true, evidence.get("has_javascript"));
        assertFalse(evidence.containsKey("script"));
    }

    @Test
    void reportsEmbeddedFiles() throws Exception {
        File pdf = tempDir.resolve("embedded-file.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            PDDocumentNameDictionary names = new PDDocumentNameDictionary(document.getDocumentCatalog());
            PDEmbeddedFilesNameTreeNode embeddedFiles = new PDEmbeddedFilesNameTreeNode();
            PDComplexFileSpecification fileSpecification = new PDComplexFileSpecification();
            fileSpecification.setFile("notes.txt");
            embeddedFiles.setNames(Map.of("notes.txt", fileSpecification));
            names.setEmbeddedFiles(embeddedFiles);
            document.getDocumentCatalog().setNames(names);
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "interactive.embedded_files");
        assertEquals("document", evidence.get("scope"));
        assertEquals(1, evidence.get("count"));
        assertEquals(List.of("notes.txt"), evidence.get("names"));
    }

    @Test
    void reportsAcroForm() throws Exception {
        File pdf = tempDir.resolve("form.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            document.addPage(new PDPage());
            PDAcroForm form = new PDAcroForm(document);
            PDTextField field = new PDTextField(form);
            field.setPartialName("title");
            form.setFields(List.of(field));
            document.getDocumentCatalog().setAcroForm(form);
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        Map<String, Object> evidence = firstEvidenceFor(result, "interactive.forms");
        assertEquals("document", evidence.get("scope"));
        assertEquals(1, evidence.get("field_count"));
        assertEquals(false, evidence.get("has_xfa"));
    }

    @Test
    void ignoresUnusedTransparencyGraphicsState() throws Exception {
        File pdf = tempDir.resolve("unused-transparent-state.pdf").toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            page.setResources(new PDResources());

            PDExtendedGraphicsState graphicsState = new PDExtendedGraphicsState();
            graphicsState.setNonStrokingAlphaConstant(0.5f);
            page.getResources().add(graphicsState);

            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.addRect(72, 500, 100, 100);
                content.fill();
            }
            document.save(pdf);
        }

        Map<String, Object> result = PdfBoxAnalyzer.analyze(pdf);

        assertFalse(hasEvidenceFor(result, "transparency.features"));
    }

    private File writeImagePdf(String name, int pixelWidth, int pixelHeight, float drawnWidthPt, float drawnHeightPt) throws Exception {
        File pdf = tempDir.resolve(name).toFile();
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            PDImageXObject image = createBlueImage(document, pixelWidth, pixelHeight);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.drawImage(image, 72, 500, drawnWidthPt, drawnHeightPt);
            }
            document.save(pdf);
        }
        return pdf;
    }

    private PDImageXObject createBlueImage(PDDocument document, int pixelWidth, int pixelHeight) throws Exception {
        BufferedImage bufferedImage = new BufferedImage(pixelWidth, pixelHeight, BufferedImage.TYPE_INT_RGB);
        for (int y = 0; y < pixelHeight; y++) {
            for (int x = 0; x < pixelWidth; x++) {
                bufferedImage.setRGB(x, y, Color.BLUE.getRGB());
            }
        }
        return LosslessFactory.createFromImage(document, bufferedImage);
    }

    private PDImageXObject createJpegImage(PDDocument document, int pixelWidth, int pixelHeight) throws Exception {
        BufferedImage bufferedImage = new BufferedImage(pixelWidth, pixelHeight, BufferedImage.TYPE_INT_RGB);
        for (int y = 0; y < pixelHeight; y++) {
            for (int x = 0; x < pixelWidth; x++) {
                bufferedImage.setRGB(x, y, Color.BLUE.getRGB());
            }
        }
        return JPEGFactory.createFromImage(document, bufferedImage);
    }

    private PDImageXObject createGrayImage(PDDocument document, int pixelWidth, int pixelHeight) throws Exception {
        BufferedImage bufferedImage = new BufferedImage(pixelWidth, pixelHeight, BufferedImage.TYPE_BYTE_GRAY);
        for (int y = 0; y < pixelHeight; y++) {
            for (int x = 0; x < pixelWidth; x++) {
                bufferedImage.setRGB(x, y, Color.WHITE.getRGB());
            }
        }
        return LosslessFactory.createFromImage(document, bufferedImage);
    }

    private Map<String, Object> firstEvidenceFor(Map<String, Object> result, String checkId) {
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> evidence = (List<Map<String, Object>>) result.get("evidence");
        return evidence.stream()
                .filter(item -> checkId.equals(item.get("check_id")))
                .findFirst()
                .orElseThrow();
    }

    private Map<String, Object> firstEvidenceFor(Map<String, Object> result, String checkId, String resourcePath) {
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> evidence = (List<Map<String, Object>>) result.get("evidence");
        return evidence.stream()
                .filter(item -> checkId.equals(item.get("check_id")) && resourcePath.equals(item.get("resource_path")))
                .findFirst()
                .orElseThrow();
    }

    private boolean hasEvidenceFor(Map<String, Object> result, String checkId) {
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> evidence = (List<Map<String, Object>>) result.get("evidence");
        return evidence.stream().anyMatch(item -> checkId.equals(item.get("check_id")));
    }

    private void assertDoubleEquals(double expected, Object actual) {
        assertEquals(expected, ((Number) actual).doubleValue(), 0.001);
    }

    private void assertBounds(Map<String, Object> evidence, double left, double bottom, double right, double top) {
        @SuppressWarnings("unchecked")
        Map<String, Object> bounds = (Map<String, Object>) evidence.get("bounds_pt");
        assertDoubleEquals(left, bounds.get("left"));
        assertDoubleEquals(bottom, bounds.get("bottom"));
        assertDoubleEquals(right, bounds.get("right"));
        assertDoubleEquals(top, bounds.get("top"));
    }

    private byte[] minimalRgbIccProfile() {
        return java.awt.color.ICC_Profile.getInstance(java.awt.color.ColorSpace.CS_sRGB).getData();
    }

    private byte[] serializeXmp(XMPMetadata xmp) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        new XmpSerializer().serialize(xmp, output, true);
        return output.toByteArray();
    }

    private String pdfxXmp() {
        return """
                <?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
                <x:xmpmeta xmlns:x="adobe:ns:meta/">
                  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
                    <rdf:Description rdf:about=""
                      xmlns:pdfx="http://ns.adobe.com/pdfx/1.3/"
                      pdfx:GTS_PDFXVersion="PDF/X-4"
                      pdfx:GTS_PDFXConformance="PDF/X-4"/>
                  </rdf:RDF>
                </x:xmpmeta>
                <?xpacket end="w"?>
                """;
    }

    private PDSeparation separationColorSpace(String colorantName) throws Exception {
        COSArray colorSpace = new COSArray();
        colorSpace.add(COSName.SEPARATION);
        colorSpace.add(COSName.getPDFName(colorantName));
        colorSpace.add(COSName.DEVICECMYK);
        colorSpace.add(type2TintTransform());
        return new PDSeparation(colorSpace);
    }

    private COSDictionary type2TintTransform() {
        COSDictionary function = new COSDictionary();
        function.setInt(COSName.FUNCTION_TYPE, 2);
        function.setItem(COSName.DOMAIN, cosArray(0, 1));
        function.setItem(COSName.getPDFName("C0"), cosArray(0, 0, 0, 0));
        function.setItem(COSName.getPDFName("C1"), cosArray(1, 1, 1, 1));
        function.setItem(COSName.getPDFName("N"), COSInteger.ONE);
        return function;
    }

    private COSArray cosArray(float... values) {
        COSArray array = new COSArray();
        for (float value : values) {
            array.add(new COSFloat(value));
        }
        return array;
    }
}
