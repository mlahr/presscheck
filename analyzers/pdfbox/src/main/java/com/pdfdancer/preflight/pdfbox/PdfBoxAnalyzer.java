package com.pdfdancer.preflight.pdfbox;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.cos.COSName;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDResources;
import org.apache.pdfbox.pdmodel.font.PDFont;

import java.io.File;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class PdfBoxAnalyzer {
    private static final ObjectMapper JSON = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);

    private PdfBoxAnalyzer() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            emit(Map.of(
                    "ok", false,
                    "analyzer", "pdfbox",
                    "error", "expected exactly one input PDF path"
            ));
            System.exit(2);
        }

        try {
            emit(analyze(Path.of(args[0]).toFile()));
        } catch (Exception exception) {
            emit(Map.of(
                    "ok", false,
                    "analyzer", "pdfbox",
                    "error", exception.getClass().getSimpleName()
            ));
            System.exit(1);
        }
    }

    static Map<String, Object> analyze(File pdfFile) throws Exception {
        try (PDDocument document = Loader.loadPDF(pdfFile)) {
            List<Map<String, Object>> evidence = new ArrayList<>();
            int pageNumber = 0;
            for (PDPage page : document.getPages()) {
                pageNumber++;
                collectPageFontEvidence(page, pageNumber, evidence);
            }

            Map<String, Object> metadata = new LinkedHashMap<>();
            metadata.put("page_count", document.getNumberOfPages());

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("ok", true);
            result.put("analyzer", "pdfbox");
            result.put("metadata", metadata);
            result.put("evidence", evidence);
            return result;
        }
    }

    private static void collectPageFontEvidence(PDPage page, int pageNumber, List<Map<String, Object>> evidence) throws Exception {
        PDResources resources = page.getResources();
        if (resources == null) {
            return;
        }

        for (COSName fontName : resources.getFontNames()) {
            PDFont font = resources.getFont(fontName);
            if (font == null || font.isEmbedded()) {
                continue;
            }

            Map<String, Object> item = new LinkedHashMap<>();
            item.put("check_id", "fonts.non_embedded");
            item.put("category", "fonts");
            item.put("page", pageNumber);
            item.put("resource_name", fontName.getName());
            item.put("font_name", font.getName());
            item.put("subtype", font.getSubType());
            item.put("embedded", false);
            evidence.add(item);
        }
    }

    private static void emit(Map<String, Object> payload) throws Exception {
        JSON.writeValue(System.out, payload);
        System.out.println();
    }
}

