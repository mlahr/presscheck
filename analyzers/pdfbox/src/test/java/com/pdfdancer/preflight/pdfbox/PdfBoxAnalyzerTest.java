package com.pdfdancer.preflight.pdfbox;

import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDFormContentStream;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.PDResources;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.apache.pdfbox.pdmodel.graphics.blend.BlendMode;
import org.apache.pdfbox.pdmodel.graphics.color.PDOutputIntent;
import org.apache.pdfbox.pdmodel.graphics.form.PDFormXObject;
import org.apache.pdfbox.pdmodel.graphics.state.PDExtendedGraphicsState;
import org.apache.pdfbox.pdmodel.graphics.image.LosslessFactory;
import org.apache.pdfbox.pdmodel.graphics.image.PDImageXObject;
import org.apache.pdfbox.util.Matrix;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.awt.Color;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.File;
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

    private Map<String, Object> firstEvidenceFor(Map<String, Object> result, String checkId) {
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> evidence = (List<Map<String, Object>>) result.get("evidence");
        return evidence.stream()
                .filter(item -> checkId.equals(item.get("check_id")))
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

    private byte[] minimalRgbIccProfile() {
        return java.awt.color.ICC_Profile.getInstance(java.awt.color.ColorSpace.CS_sRGB).getData();
    }
}
