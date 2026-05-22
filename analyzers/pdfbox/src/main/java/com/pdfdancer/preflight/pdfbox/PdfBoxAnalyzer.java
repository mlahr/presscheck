package com.pdfdancer.preflight.pdfbox;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.contentstream.PDFGraphicsStreamEngine;
import org.apache.pdfbox.contentstream.operator.Operator;
import org.apache.pdfbox.cos.COSArray;
import org.apache.pdfbox.cos.COSBase;
import org.apache.pdfbox.cos.COSName;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDResources;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.font.PDFont;
import org.apache.pdfbox.pdmodel.graphics.PDXObject;
import org.apache.pdfbox.pdmodel.graphics.blend.BlendMode;
import org.apache.pdfbox.pdmodel.graphics.color.PDColor;
import org.apache.pdfbox.pdmodel.graphics.color.PDColorSpace;
import org.apache.pdfbox.pdmodel.graphics.color.PDDeviceCMYK;
import org.apache.pdfbox.pdmodel.graphics.color.PDDeviceGray;
import org.apache.pdfbox.pdmodel.graphics.color.PDDeviceN;
import org.apache.pdfbox.pdmodel.graphics.color.PDDeviceRGB;
import org.apache.pdfbox.pdmodel.graphics.color.PDICCBased;
import org.apache.pdfbox.pdmodel.graphics.color.PDIndexed;
import org.apache.pdfbox.pdmodel.graphics.color.PDOutputIntent;
import org.apache.pdfbox.pdmodel.graphics.color.PDSeparation;
import org.apache.pdfbox.pdmodel.graphics.form.PDFormXObject;
import org.apache.pdfbox.pdmodel.graphics.form.PDTransparencyGroup;
import org.apache.pdfbox.pdmodel.graphics.image.PDImage;
import org.apache.pdfbox.pdmodel.graphics.image.PDImageXObject;
import org.apache.pdfbox.pdmodel.graphics.state.PDGraphicsState;
import org.apache.pdfbox.pdmodel.graphics.state.PDExtendedGraphicsState;
import org.apache.pdfbox.pdmodel.graphics.state.RenderingMode;
import org.apache.pdfbox.util.Matrix;
import org.apache.pdfbox.util.Vector;

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
            collectOutputIntentEvidence(document, evidence);
            int pageNumber = 0;
            for (PDPage page : document.getPages()) {
                pageNumber++;
                collectPageFontEvidence(page, pageNumber, evidence);
                collectPageContentEvidence(page, pageNumber, evidence);
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

    private static void collectOutputIntentEvidence(PDDocument document, List<Map<String, Object>> evidence) {
        List<PDOutputIntent> outputIntents = document.getDocumentCatalog().getOutputIntents();
        List<Map<String, Object>> outputIntentItems = new ArrayList<>();
        for (PDOutputIntent outputIntent : outputIntents) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("subtype", outputIntent.getCOSObject().getNameAsString(COSName.S));
            item.put("output_condition", outputIntent.getOutputCondition());
            item.put("output_condition_identifier", outputIntent.getOutputConditionIdentifier());
            item.put("registry_name", outputIntent.getRegistryName());
            item.put("info", outputIntent.getInfo());
            item.put("has_dest_output_profile", outputIntent.getDestOutputIntent() != null);
            outputIntentItems.add(item);
        }

        Map<String, Object> item = new LinkedHashMap<>();
        item.put("check_id", "color.output_intents");
        item.put("category", "color");
        item.put("scope", "document");
        item.put("count", outputIntents.size());
        item.put("output_intents", outputIntentItems);
        evidence.add(item);
    }

    private static void collectPageContentEvidence(PDPage page, int pageNumber, List<Map<String, Object>> evidence) throws IOException {
        new PageContentCollector(page, pageNumber, evidence).processPage(page);
    }

    private static void emit(Map<String, Object> payload) throws Exception {
        JSON.writeValue(System.out, payload);
        System.out.println();
    }

    private static final class PageContentCollector extends PDFGraphicsStreamEngine {
        private final int pageNumber;
        private final List<Map<String, Object>> evidence;
        private final List<String> resourcePath = new ArrayList<>();
        private final Map<String, TextSizeGroup> textSizeGroups = new LinkedHashMap<>();
        private final Map<String, SpecialColorGroup> specialColorGroups = new LinkedHashMap<>();
        private final Map<String, OverprintGroup> overprintGroups = new LinkedHashMap<>();

        private PageContentCollector(PDPage page, int pageNumber, List<Map<String, Object>> evidence) {
            super(page);
            this.pageNumber = pageNumber;
            this.evidence = evidence;
        }

        @Override
        public void processPage(PDPage page) throws IOException {
            super.processPage(page);
            flushTextSizeEvidence();
            flushSpecialColorEvidence();
            flushOverprintEvidence();
        }

        @Override
        protected void processOperator(Operator operator, List<COSBase> operands) throws IOException {
            if ("gs".equals(operator.getName()) && !operands.isEmpty() && operands.get(0) instanceof COSName resourceName) {
                PDResources resources = getResources();
                if (resources != null) {
                    PDExtendedGraphicsState graphicsState = resources.getExtGState(resourceName);
                    if (graphicsState != null) {
                        collectTransparencyState(resourceName, graphicsState);
                    }
                }
            }

            if ("Do".equals(operator.getName()) && !operands.isEmpty() && operands.get(0) instanceof COSName resourceName) {
                PDResources resources = getResources();
                if (resources != null) {
                    PDXObject xObject = resources.getXObject(resourceName);
                    if (xObject instanceof PDImageXObject image) {
                        collectObjectBounds(resourceName, "image", imageBounds());
                        collectImage(resourceName, image);
                        return;
                    }
                    if (xObject instanceof PDTransparencyGroup) {
                        collectTransparencyGroup(resourceName);
                    }
                    if (xObject instanceof PDFormXObject form) {
                        collectObjectBounds(resourceName, "form", formBounds(form));
                        resourcePath.add(resourceName.getName());
                        try {
                            super.processOperator(operator, operands);
                        } finally {
                            resourcePath.remove(resourcePath.size() - 1);
                        }
                        return;
                    }
                }
            }
            super.processOperator(operator, operands);
        }

        @Override
        protected void showGlyph(Matrix textRenderingMatrix, PDFont font, int code, Vector displacement) throws IOException {
            collectTextSize(textRenderingMatrix, font);
            RenderingMode renderingMode = getGraphicsState().getTextState().getRenderingMode();
            if (renderingMode.isFill()) {
                collectPaintState("text_fill", false);
            }
            if (renderingMode.isStroke()) {
                collectPaintState("text_stroke", true);
            }
            super.showGlyph(textRenderingMatrix, font, code, displacement);
        }

        private void collectTextSize(Matrix textRenderingMatrix, PDFont font) {
            RenderingMode renderingMode = getGraphicsState().getTextState().getRenderingMode();
            if (!renderingMode.isFill() && !renderingMode.isStroke()) {
                return;
            }

            String fontName = font.getName();
            String subtype = font.getSubType();
            String path = currentResourcePath();
            double effectiveSize = round2(Math.abs(textRenderingMatrix.getScalingFactorY()));
            double horizontalSize = round2(Math.abs(textRenderingMatrix.getScalingFactorX()));
            String key = pageNumber + "|" + path + "|" + fontName + "|" + subtype + "|" + effectiveSize + "|" + horizontalSize;
            TextSizeGroup group = textSizeGroups.get(key);
            if (group == null) {
                group = new TextSizeGroup(fontName, subtype, path, effectiveSize, horizontalSize);
                textSizeGroups.put(key, group);
            }
            group.occurrences++;
        }

        private void flushTextSizeEvidence() {
            for (TextSizeGroup group : textSizeGroups.values()) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("check_id", "fonts.text_size");
                item.put("category", "fonts");
                item.put("page", pageNumber);
                if (!group.resourcePath.isEmpty()) {
                    item.put("resource_path", group.resourcePath);
                }
                item.put("font_name", group.fontName);
                item.put("subtype", group.subtype);
                item.put("effective_size_pt", group.effectiveSizePt);
                item.put("horizontal_size_pt", group.horizontalSizePt);
                item.put("occurrences", group.occurrences);
                evidence.add(item);
            }
        }

        private void flushSpecialColorEvidence() {
            for (SpecialColorGroup group : specialColorGroups.values()) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("check_id", "color.special_color_usage");
                item.put("category", "color");
                item.put("page", pageNumber);
                if (!group.resourcePath.isEmpty()) {
                    item.put("resource_path", group.resourcePath);
                }
                item.put("paint_operation", group.paintOperation);
                item.put("paint_role", group.paintRole);
                item.put("color_space_name", group.colorSpaceName);
                item.put("color_space_family", group.colorSpaceFamily);
                item.put("colorants", group.colorants);
                item.put("occurrences", group.occurrences);
                evidence.add(item);
            }
        }

        private void flushOverprintEvidence() {
            for (OverprintGroup group : overprintGroups.values()) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("check_id", "graphics.overprint_usage");
                item.put("category", "graphics");
                item.put("page", pageNumber);
                if (!group.resourcePath.isEmpty()) {
                    item.put("resource_path", group.resourcePath);
                }
                item.put("paint_operation", group.paintOperation);
                item.put("paint_role", group.paintRole);
                item.put("overprint_mode", group.overprintMode);
                item.put("occurrences", group.occurrences);
                evidence.add(item);
            }
        }

        private void collectObjectBounds(COSName resourceName, String objectType, Map<String, Double> bounds) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("check_id", "geometry.object_bounds");
            item.put("category", "geometry");
            item.put("page", pageNumber);
            item.put("resource_name", resourceName.getName());
            item.put("resource_path", resourcePath(resourceName));
            item.put("object_type", objectType);
            item.put("bounds_pt", bounds);
            evidence.add(item);
        }

        private Map<String, Double> imageBounds() {
            Matrix ctm = getGraphicsState().getCurrentTransformationMatrix();
            return transformedBounds(ctm, 0, 0, 1, 1);
        }

        private Map<String, Double> formBounds(PDFormXObject form) {
            Matrix ctm = getGraphicsState().getCurrentTransformationMatrix().clone();
            ctm.concatenate(form.getMatrix());
            PDRectangle bbox = form.getBBox();
            return transformedBounds(ctm, bbox.getLowerLeftX(), bbox.getLowerLeftY(), bbox.getUpperRightX(), bbox.getUpperRightY());
        }

        private Map<String, Double> transformedBounds(Matrix matrix, float left, float bottom, float right, float top) {
            Point2D.Float lowerLeft = matrix.transformPoint(left, bottom);
            Point2D.Float lowerRight = matrix.transformPoint(right, bottom);
            Point2D.Float upperLeft = matrix.transformPoint(left, top);
            Point2D.Float upperRight = matrix.transformPoint(right, top);

            double minX = Math.min(Math.min(lowerLeft.x, lowerRight.x), Math.min(upperLeft.x, upperRight.x));
            double maxX = Math.max(Math.max(lowerLeft.x, lowerRight.x), Math.max(upperLeft.x, upperRight.x));
            double minY = Math.min(Math.min(lowerLeft.y, lowerRight.y), Math.min(upperLeft.y, upperRight.y));
            double maxY = Math.max(Math.max(lowerLeft.y, lowerRight.y), Math.max(upperLeft.y, upperRight.y));

            Map<String, Double> bounds = new LinkedHashMap<>();
            bounds.put("left", minX);
            bounds.put("bottom", minY);
            bounds.put("right", maxX);
            bounds.put("top", maxY);
            return bounds;
        }

        private void collectTransparencyState(COSName resourceName, PDExtendedGraphicsState graphicsState) {
            List<String> features = new ArrayList<>();
            Map<String, Object> item = transparencyEvidence(resourceName);

            Float strokingAlpha = graphicsState.getStrokingAlphaConstant();
            if (strokingAlpha != null && strokingAlpha < 1.0f) {
                features.add("stroking_alpha");
                item.put("stroking_alpha", strokingAlpha);
            }

            Float nonStrokingAlpha = graphicsState.getNonStrokingAlphaConstant();
            if (nonStrokingAlpha != null && nonStrokingAlpha < 1.0f) {
                features.add("non_stroking_alpha");
                item.put("non_stroking_alpha", nonStrokingAlpha);
            }

            if (graphicsState.getSoftMask() != null) {
                features.add("soft_mask");
                item.put("soft_mask", true);
            }

            if (graphicsState.getCOSObject().containsKey(COSName.BM)) {
                BlendMode blendMode = graphicsState.getBlendMode();
                if (blendMode != null && !COSName.NORMAL.equals(blendMode.getCOSName())) {
                    features.add("blend_mode");
                    item.put("blend_mode", blendMode.getCOSName().getName());
                }
            }

            if (!features.isEmpty()) {
                item.put("features", features);
                evidence.add(item);
            }
        }

        private void collectTransparencyGroup(COSName resourceName) {
            Map<String, Object> item = transparencyEvidence(resourceName);
            item.put("features", List.of("transparency_group"));
            item.put("transparency_group", true);
            evidence.add(item);
        }

        private Map<String, Object> transparencyEvidence(COSName resourceName) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("check_id", "transparency.features");
            item.put("category", "transparency");
            item.put("page", pageNumber);
            item.put("resource_name", resourceName.getName());
            item.put("resource_path", resourcePath(resourceName));
            return item;
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
            item.put("resource_path", resourcePath(resourceName));
            item.put("pixel_width", pixelWidth);
            item.put("pixel_height", pixelHeight);
            item.put("drawn_width_pt", drawnWidthPt);
            item.put("drawn_height_pt", drawnHeightPt);
            item.put("x_dpi", xDpi);
            item.put("y_dpi", yDpi);
            item.put("min_dpi", Math.min(xDpi, yDpi));
            item.put("color_space_name", colorSpace.getName());
            item.put("color_space_family", colorSpaceFamily(colorSpace));
            item.put("filters", filters(image.getCOSObject().getFilters()));
            item.put("bits_per_component", image.getBitsPerComponent());
            item.put("interpolate", image.getInterpolate());
            item.put("image_mask", image.isStencil());
            item.put("has_soft_mask", image.getSoftMask() != null);
            item.put("has_explicit_mask", image.getCOSObject().containsKey(COSName.MASK));
            evidence.add(item);
            collectSpecialColor("image", "non_stroking", resourcePath(resourceName), colorSpace);
            collectOverprint("image", false, resourcePath(resourceName));
        }

        private void collectPaintState(String paintOperation, boolean stroking) {
            PDGraphicsState graphicsState = getGraphicsState();
            PDColor color = stroking ? graphicsState.getStrokingColor() : graphicsState.getNonStrokingColor();
            if (color != null) {
                collectSpecialColor(
                        paintOperation,
                        stroking ? "stroking" : "non_stroking",
                        currentResourcePath(),
                        color.getColorSpace()
                );
            }
            collectOverprint(paintOperation, stroking, currentResourcePath());
        }

        private void collectSpecialColor(
                String paintOperation,
                String paintRole,
                String path,
                PDColorSpace colorSpace
        ) {
            List<String> colorants = colorants(colorSpace);
            if (colorants.isEmpty()) {
                return;
            }

            String colorSpaceFamily = colorSpaceFamily(colorSpace);
            String key = pageNumber + "|" + path + "|" + paintOperation + "|" + paintRole + "|"
                    + colorSpace.getName() + "|" + colorSpaceFamily + "|" + String.join(",", colorants);
            SpecialColorGroup group = specialColorGroups.get(key);
            if (group == null) {
                group = new SpecialColorGroup(
                        path,
                        paintOperation,
                        paintRole,
                        colorSpace.getName(),
                        colorSpaceFamily,
                        colorants
                );
                specialColorGroups.put(key, group);
            }
            group.occurrences++;
        }

        private void collectOverprint(String paintOperation, boolean stroking, String path) {
            PDGraphicsState graphicsState = getGraphicsState();
            boolean overprint = stroking ? graphicsState.isOverprint() : graphicsState.isNonStrokingOverprint();
            if (!overprint) {
                return;
            }

            String paintRole = stroking ? "stroking" : "non_stroking";
            int overprintMode = graphicsState.getOverprintMode();
            String key = pageNumber + "|" + path + "|" + paintOperation + "|" + paintRole + "|" + overprintMode;
            OverprintGroup group = overprintGroups.get(key);
            if (group == null) {
                group = new OverprintGroup(path, paintOperation, paintRole, overprintMode);
                overprintGroups.put(key, group);
            }
            group.occurrences++;
        }

        private String resourcePath(COSName resourceName) {
            if (resourcePath.isEmpty()) {
                return resourceName.getName();
            }
            List<String> segments = new ArrayList<>(resourcePath);
            segments.add(resourceName.getName());
            return String.join("/", segments);
        }

        private String currentResourcePath() {
            if (resourcePath.isEmpty()) {
                return "";
            }
            return String.join("/", resourcePath);
        }

        private double round2(double value) {
            return Math.round(value * 100.0) / 100.0;
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

        private List<String> colorants(PDColorSpace colorSpace) {
            if (colorSpace instanceof PDSeparation separation) {
                return List.of(separation.getColorantName());
            }
            if (colorSpace instanceof PDDeviceN deviceN) {
                return deviceN.getColorantNames();
            }
            return List.of();
        }

        private List<String> filters(COSBase filters) {
            if (filters instanceof COSName filter) {
                return List.of(filter.getName());
            }
            if (filters instanceof COSArray filterArray) {
                List<String> names = new ArrayList<>();
                for (COSBase filter : filterArray) {
                    if (filter instanceof COSName filterName) {
                        names.add(filterName.getName());
                    }
                }
                return names;
            }
            return List.of();
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
            collectPaintState("path_stroke", true);
        }

        @Override
        public void fillPath(int windingRule) {
            collectPaintState("path_fill", false);
        }

        @Override
        public void fillAndStrokePath(int windingRule) {
            collectPaintState("path_fill", false);
            collectPaintState("path_stroke", true);
        }

        @Override
        public void shadingFill(COSName shadingName) {
        }

        private static final class TextSizeGroup {
            private final String fontName;
            private final String subtype;
            private final String resourcePath;
            private final double effectiveSizePt;
            private final double horizontalSizePt;
            private int occurrences;

            private TextSizeGroup(
                    String fontName,
                    String subtype,
                    String resourcePath,
                    double effectiveSizePt,
                    double horizontalSizePt
            ) {
                this.fontName = fontName;
                this.subtype = subtype;
                this.resourcePath = resourcePath;
                this.effectiveSizePt = effectiveSizePt;
                this.horizontalSizePt = horizontalSizePt;
                this.occurrences = 0;
            }
        }

        private static final class SpecialColorGroup {
            private final String resourcePath;
            private final String paintOperation;
            private final String paintRole;
            private final String colorSpaceName;
            private final String colorSpaceFamily;
            private final List<String> colorants;
            private int occurrences;

            private SpecialColorGroup(
                    String resourcePath,
                    String paintOperation,
                    String paintRole,
                    String colorSpaceName,
                    String colorSpaceFamily,
                    List<String> colorants
            ) {
                this.resourcePath = resourcePath;
                this.paintOperation = paintOperation;
                this.paintRole = paintRole;
                this.colorSpaceName = colorSpaceName;
                this.colorSpaceFamily = colorSpaceFamily;
                this.colorants = colorants;
                this.occurrences = 0;
            }
        }

        private static final class OverprintGroup {
            private final String resourcePath;
            private final String paintOperation;
            private final String paintRole;
            private final int overprintMode;
            private int occurrences;

            private OverprintGroup(String resourcePath, String paintOperation, String paintRole, int overprintMode) {
                this.resourcePath = resourcePath;
                this.paintOperation = paintOperation;
                this.paintRole = paintRole;
                this.overprintMode = overprintMode;
                this.occurrences = 0;
            }
        }
    }
}
