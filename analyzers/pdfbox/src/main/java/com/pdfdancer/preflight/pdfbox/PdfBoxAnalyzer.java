package com.pdfdancer.preflight.pdfbox;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.contentstream.PDFGraphicsStreamEngine;
import org.apache.pdfbox.contentstream.operator.Operator;
import org.apache.pdfbox.cos.COSBase;
import org.apache.pdfbox.cos.COSName;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDResources;
import org.apache.pdfbox.pdmodel.font.PDFont;
import org.apache.pdfbox.pdmodel.graphics.PDXObject;
import org.apache.pdfbox.pdmodel.graphics.color.PDColorSpace;
import org.apache.pdfbox.pdmodel.graphics.color.PDDeviceCMYK;
import org.apache.pdfbox.pdmodel.graphics.color.PDDeviceGray;
import org.apache.pdfbox.pdmodel.graphics.color.PDDeviceN;
import org.apache.pdfbox.pdmodel.graphics.color.PDDeviceRGB;
import org.apache.pdfbox.pdmodel.graphics.color.PDICCBased;
import org.apache.pdfbox.pdmodel.graphics.color.PDIndexed;
import org.apache.pdfbox.pdmodel.graphics.color.PDSeparation;
import org.apache.pdfbox.pdmodel.graphics.image.PDImage;
import org.apache.pdfbox.pdmodel.graphics.image.PDImageXObject;
import org.apache.pdfbox.util.Matrix;

import java.awt.geom.Point2D;
import java.io.File;
import java.io.IOException;
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
                collectPageImageEvidence(page, pageNumber, evidence);
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

    private static void collectPageImageEvidence(PDPage page, int pageNumber, List<Map<String, Object>> evidence) throws IOException {
        new ImagePlacementCollector(page, pageNumber, evidence).processPage(page);
    }

    private static void emit(Map<String, Object> payload) throws Exception {
        JSON.writeValue(System.out, payload);
        System.out.println();
    }

    private static final class ImagePlacementCollector extends PDFGraphicsStreamEngine {
        private final int pageNumber;
        private final List<Map<String, Object>> evidence;

        private ImagePlacementCollector(PDPage page, int pageNumber, List<Map<String, Object>> evidence) {
            super(page);
            this.pageNumber = pageNumber;
            this.evidence = evidence;
        }

        @Override
        protected void processOperator(Operator operator, List<COSBase> operands) throws IOException {
            if ("Do".equals(operator.getName()) && !operands.isEmpty() && operands.get(0) instanceof COSName resourceName) {
                PDXObject xObject = getResources().getXObject(resourceName);
                if (xObject instanceof PDImageXObject image) {
                    collectImage(resourceName, image);
                    return;
                }
            }
            super.processOperator(operator, operands);
        }

        private void collectImage(COSName resourceName, PDImageXObject image) throws IOException {
            Matrix ctm = getGraphicsState().getCurrentTransformationMatrix();
            double drawnWidthPt = ctm.getScalingFactorX();
            double drawnHeightPt = ctm.getScalingFactorY();
            if (drawnWidthPt <= 0 || drawnHeightPt <= 0) {
                return;
            }

            int pixelWidth = image.getWidth();
            int pixelHeight = image.getHeight();
            double xDpi = pixelWidth / (drawnWidthPt / 72.0);
            double yDpi = pixelHeight / (drawnHeightPt / 72.0);
            PDColorSpace colorSpace = image.getColorSpace();

            Map<String, Object> item = new LinkedHashMap<>();
            item.put("check_id", "images.effective_resolution");
            item.put("category", "images");
            item.put("page", pageNumber);
            item.put("resource_name", resourceName.getName());
            item.put("pixel_width", pixelWidth);
            item.put("pixel_height", pixelHeight);
            item.put("drawn_width_pt", drawnWidthPt);
            item.put("drawn_height_pt", drawnHeightPt);
            item.put("x_dpi", xDpi);
            item.put("y_dpi", yDpi);
            item.put("min_dpi", Math.min(xDpi, yDpi));
            item.put("color_space_name", colorSpace.getName());
            item.put("color_space_family", colorSpaceFamily(colorSpace));
            evidence.add(item);
        }

        private String colorSpaceFamily(PDColorSpace colorSpace) {
            if (colorSpace instanceof PDDeviceRGB) {
                return "DeviceRGB";
            }
            if (colorSpace instanceof PDDeviceCMYK) {
                return "DeviceCMYK";
            }
            if (colorSpace instanceof PDDeviceGray) {
                return "DeviceGray";
            }
            if (colorSpace instanceof PDIndexed) {
                return "Indexed";
            }
            if (colorSpace instanceof PDSeparation) {
                return "Separation";
            }
            if (colorSpace instanceof PDDeviceN) {
                return "DeviceN";
            }
            if (colorSpace instanceof PDICCBased iccBased) {
                int components = iccBased.getNumberOfComponents();
                if (components == 1) {
                    return "ICCBasedGray";
                }
                if (components == 3) {
                    return "ICCBasedRGB";
                }
                if (components == 4) {
                    return "ICCBasedCMYK";
                }
            }
            return "Other";
        }

        @Override
        public void drawImage(PDImage pdImage) {
            // Direct image XObjects are handled in processOperator so the resource name is available.
        }

        @Override
        public void appendRectangle(Point2D point2D, Point2D point2D1, Point2D point2D2, Point2D point2D3) {
        }

        @Override
        public void clip(int windingRule) {
        }

        @Override
        public void moveTo(float x, float y) {
        }

        @Override
        public void lineTo(float x, float y) {
        }

        @Override
        public void curveTo(float x1, float y1, float x2, float y2, float x3, float y3) {
        }

        @Override
        public Point2D getCurrentPoint() {
            return null;
        }

        @Override
        public void closePath() {
        }

        @Override
        public void endPath() {
        }

        @Override
        public void strokePath() {
        }

        @Override
        public void fillPath(int windingRule) {
        }

        @Override
        public void fillAndStrokePath(int windingRule) {
        }

        @Override
        public void shadingFill(COSName shadingName) {
        }
    }
}
