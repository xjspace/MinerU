from loguru import logger

from magic_pdf.libs.boxbase import __is_overlaps_y_exceeds_threshold, get_minbox_if_overlap_by_ratio, \
    calculate_overlap_area_in_bbox1_area_ratio
from magic_pdf.libs.drop_tag import DropTag
from magic_pdf.libs.ocr_content_type import ContentType
from magic_pdf.pre_proc.ocr_fix_block_logic import fix_image_block, fix_table_block


# 将每一个line中的span从左到右排序
def line_sort_spans_by_left_to_right(lines):
    line_objects = []
    for line in lines:
        # 按照x0坐标排序
        line.sort(key=lambda span: span['bbox'][0])
        line_bbox = [
            min(span['bbox'][0] for span in line),  # x0
            min(span['bbox'][1] for span in line),  # y0
            max(span['bbox'][2] for span in line),  # x1
            max(span['bbox'][3] for span in line),  # y1
        ]
        line_objects.append({
            "bbox": line_bbox,
            "spans": line,
        })
    return line_objects


def merge_spans_to_line(spans):
    if len(spans) == 0:
        return []
    else:
        # 按照y0坐标排序
        spans.sort(key=lambda span: span['bbox'][1])

        lines = []
        current_line = [spans[0]]
        for span in spans[1:]:
            # 如果当前的span类型为"interline_equation" 或者 当前行中已经有"interline_equation"
            # image和table类型，同上
            if span['type'] in [ContentType.InterlineEquation, ContentType.Image, ContentType.Table] or any(
                    s['type'] in [ContentType.InterlineEquation, ContentType.Image, ContentType.Table] for s in
                    current_line):
                # 则开始新行
                lines.append(current_line)
                current_line = [span]
                continue

            # 如果当前的span与当前行的最后一个span在y轴上重叠，则添加到当前行
            if __is_overlaps_y_exceeds_threshold(span['bbox'], current_line[-1]['bbox']):
                current_line.append(span)
            else:
                # 否则，开始新行
                lines.append(current_line)
                current_line = [span]

        # 添加最后一行
        if current_line:
            lines.append(current_line)

        return lines


def merge_spans_to_line_by_layout(spans, layout_bboxes):
    lines = []
    new_spans = []
    dropped_spans = []
    for item in layout_bboxes:
        layout_bbox = item['layout_bbox']
        # 遍历spans,将每个span放入对应的layout中
        layout_sapns = []
        for span in spans:
            if calculate_overlap_area_in_bbox1_area_ratio(span['bbox'], layout_bbox) > 0.6:
                layout_sapns.append(span)
        # 如果layout_sapns不为空，则放入new_spans中
        if len(layout_sapns) > 0:
            new_spans.append(layout_sapns)
            # 从spans删除已经放入layout_sapns中的span
            for layout_sapn in layout_sapns:
                spans.remove(layout_sapn)

    if len(new_spans) > 0:
        for layout_sapns in new_spans:
            layout_lines = merge_spans_to_line(layout_sapns)
            lines.extend(layout_lines)

    # 对line中的span进行排序
    lines = line_sort_spans_by_left_to_right(lines)

    for span in spans:
        span['tag'] = DropTag.NOT_IN_LAYOUT
        dropped_spans.append(span)

    return lines, dropped_spans


def merge_lines_to_block(lines):
    # 目前不做block拼接,先做个结构,每个block中只有一个line,block的bbox就是line的bbox
    blocks = []
    for line in lines:
        blocks.append(
            {
                "bbox": line["bbox"],
                "lines": [line],
            }
        )
    return blocks


def sort_blocks_by_layout(all_bboxes, layout_bboxes):
    new_blocks = []
    sort_blocks = []
    for item in layout_bboxes:
        layout_bbox = item['layout_bbox']

        # 遍历blocks,将每个blocks放入对应的layout中
        layout_blocks = []
        for block in all_bboxes:
            # 如果是footnote则跳过
            if block[7] == 'footnote':
                continue
            block_bbox = [block[0], block[1], block[2], block[3]]
            if calculate_overlap_area_in_bbox1_area_ratio(block_bbox, layout_bbox) > 0.8:
                layout_blocks.append(block)

        # 如果layout_blocks不为空，则放入new_blocks中
        if len(layout_blocks) > 0:
            new_blocks.append(layout_blocks)
            # 从spans删除已经放入layout_sapns中的span
            for layout_block in layout_blocks:
                all_bboxes.remove(layout_block)

    # 如果new_blocks不为空，则对new_blocks中每个block进行排序
    if len(new_blocks) > 0:
        for bboxes_in_layout_block in new_blocks:
            bboxes_in_layout_block.sort(key=lambda x: x[1])  # 一个layout内部的box，按照y0自上而下排序
            sort_blocks.extend(bboxes_in_layout_block)

    # sort_blocks中已经包含了当前页面所有最终留下的block，且已经排好了顺序
    return sort_blocks


def fill_spans_in_blocks(blocks, spans):
    block_with_spans = []
    for block in blocks:
        block_type = block[7]
        block_bbox = block[0:4]
        block_dict = {
            'block_type': block_type,
            'bbox': block_bbox,
        }
        block_spans = []
        for span in spans:
            span_bbox = span['bbox']
            if calculate_overlap_area_in_bbox1_area_ratio(span_bbox, block_bbox) > 0.8:
                block_spans.append(span)
        block_dict['spans'] = block_spans
        block_with_spans.append(block_dict)

        # 从spans删除已经放入block_spans中的span
        if len(block_spans) > 0:
            for span in block_spans:
                spans.remove(span)

    return block_with_spans


def fix_block_spans(block_with_spans, img_blocks, table_blocks):
    fix_blocks = []
    for block in block_with_spans:
        block_type = block['block_type']
        # 只有type为image_block和table_block才需要处理
        if block_type == 'image_block':
            block = fix_image_block(block, img_blocks)
        elif block_type == 'table_block':
            block = fix_table_block(block, table_blocks)
        elif block_type == 'text_block':
            pass
        elif block_type == 'title_block':
            pass
        elif block_type == 'interline_equation_block':
            pass
        else:
            continue
        fix_blocks.append(block)
    return fix_blocks
