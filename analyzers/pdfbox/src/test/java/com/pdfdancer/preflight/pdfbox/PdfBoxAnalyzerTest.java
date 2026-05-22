package com.pdfdancer.preflight.pdfbox;

import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

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
}
