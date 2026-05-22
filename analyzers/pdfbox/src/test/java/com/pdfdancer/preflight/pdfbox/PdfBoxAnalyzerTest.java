package com.pdfdancer.preflight.pdfbox;

import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.apache.pdfbox.pdmodel.graphics.image.LosslessFactory;
import org.apache.pdfbox.pdmodel.graphics.image.PDImageXObject;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.awt.Color;
import java.awt.image.BufferedImage;
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

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> evidence = (List<Map<String, Object>>) result.get("evidence");
        assertFalse(evidence.isEmpty());
        assertEquals("fonts.non_embedded", evidence.get(0).get("check_id"));
        assertEquals("fonts", evidence.get(0).get("category"));
        assertEquals(1, evidence.get(0).get("page"));
        assertEquals(false, evidence.get(0).get("embedded"));
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

    private File writeImagePdf(String name, int pixelWidth, int pixelHeight, float drawnWidthPt, float drawnHeightPt) throws Exception {
        File pdf = tempDir.resolve(name).toFile();
        BufferedImage bufferedImage = new BufferedImage(pixelWidth, pixelHeight, BufferedImage.TYPE_INT_RGB);
        for (int y = 0; y < pixelHeight; y++) {
            for (int x = 0; x < pixelWidth; x++) {
                bufferedImage.setRGB(x, y, Color.BLUE.getRGB());
            }
        }

        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage();
            document.addPage(page);
            PDImageXObject image = LosslessFactory.createFromImage(document, bufferedImage);
            try (PDPageContentStream content = new PDPageContentStream(document, page)) {
                content.drawImage(image, 72, 500, drawnWidthPt, drawnHeightPt);
            }
            document.save(pdf);
        }
        return pdf;
    }

    private Map<String, Object> firstEvidenceFor(Map<String, Object> result, String checkId) {
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> evidence = (List<Map<String, Object>>) result.get("evidence");
        return evidence.stream()
                .filter(item -> checkId.equals(item.get("check_id")))
                .findFirst()
                .orElseThrow();
    }

    private void assertDoubleEquals(double expected, Object actual) {
        assertEquals(expected, ((Number) actual).doubleValue(), 0.001);
    }
}
