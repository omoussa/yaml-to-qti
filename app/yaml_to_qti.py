import os

import yaml
from lxml.etree import Element, ElementTree, SubElement, tostring

from app.categorization_qti import convert_categorization_to_qti
from app.essay_qti import convert_essay_to_qti
from app.file_upload_qti import convert_file_upload_to_qti
from app.fitb_qti import convert_fill_in_the_blank_to_qti
from app.formula_qti import convert_formula_to_qti
from app.hotspot_qti import convert_hotspot_to_qti
from app.ma_qti import convert_multiple_answer_to_qti
from app.matching_qti import convert_matching_to_qti
from app.mc_qti import convert_multiple_choice_to_qti
from app.numeric_qti import convert_numerical_to_qti
from app.ordering_qti import convert_ordering_to_qti
from app.string_utils import sanitize_text_for_import
from app.true_false_qti import convert_true_false_to_qti
from html import escape


def create_feedback_tree(element, ident, text):
    if not text:
        return
    itemfeedback = SubElement(element, "itemfeedback", ident=ident)
    flowmat = SubElement(itemfeedback, "flow_mat")
    material = SubElement(flowmat, "material")
    mattext = SubElement(material, "mattext", texttype="text/plain")
    feedback_text = sanitize_text_for_import(text)
    mattext.text = feedback_text


def standard_question_start(section, question_type, question_obj):
    xml_element = SubElement(
        section, "item", ident=question_obj["id"], title=question_obj["title"]
    )

    # Add metadata
    itemmetadata = SubElement(xml_element, "itemmetadata")
    qtimetadata = SubElement(itemmetadata, "qtimetadata")
    # qtimetadatafield_points = SubElement(qtimetadata, 'qtimetadatafield')
    # SubElement(qtimetadatafield_points, 'fieldlabel').text = 'points_possible'
    # SubElement(qtimetadatafield_points, 'fieldentry').text = str(question_obj['points'])
    qtimetadatafield_type = SubElement(qtimetadata, "qtimetadatafield")
    SubElement(qtimetadatafield_type, "fieldlabel").text = "question_type"
    SubElement(qtimetadatafield_type, "fieldentry").text = f"{question_type}_question"

    # not all question types support calculators, but those that do seem to do so the same way
    if "calculator" in question_obj:
        qtimetadatafield_calculator = SubElement(qtimetadata, "qtimetadatafield")
        SubElement(qtimetadatafield_calculator, "fieldlabel").text = "calculator_type"
        SubElement(qtimetadatafield_calculator, "fieldentry").text = question_obj[
            "calculator"
        ]

    presentation = SubElement(xml_element, "presentation")

    # this is kind of annoyingly specific, but hot spot questions handle
    #  question text and figure placement differently than everything else
    # just return what we have and let the converter handle the rest
    if question_type == "hot_spot":
        return xml_element

    material = SubElement(presentation, "material")
    mattext = SubElement(material, "mattext", texttype="text/plain")
    mattext.text = sanitize_text_for_import(question_obj["text"])

    # Add figure if available and not empty
    # TODO: come up with some approach similar to how LaTeX is parsed into
    #  MathML that might allow us to position images wherever we want instead of
    #  always appending them after a question's text
    # Ideally this would support multiple images, and potentially also sizing rules for
    #  each.
    # Maybe start with using standard Markdown syntax?

    figure = question_obj.get("figure")
    
    #old code
    #if "figure" in question_obj and question_obj["figure"]:
    #    figure_path_parts = question_obj["figure"].split("/")
    #    filename = figure_path_parts[-1]
    #    mattext.text += f"<img src='$IMS-CC-FILEBASE$/media/{filename}' alt='Figure' />"

    
    #This reads the new figure_alt field in the yaml and safely handles quotes and ampersands. 
    #Missing or null values fall back to "Figure"; 
    #an explicit empty string remains empty for decorative images.
    
    if figure:
        filename = figure.rsplit("/", 1)[-1]

        alt_text = question_obj.get("figure_alt")
        if alt_text is None:
            alt_text = "Figure"
        elif not isinstance(alt_text, str):
            raise ValueError(
                f"Question {question_obj['id']}: "
                "figure_alt must be a string or null."
            )

        src = escape(
            f"$IMS-CC-FILEBASE$/media/{filename}",
            quote=True,
        )
        alt = escape(alt_text, quote=True)

        mattext.text += f'<img src="{src}" alt="{alt}" />'

    
    return xml_element


def yaml_to_qti(yaml_file=None, shuffle_mult=False, output_folder=None):
    # TODO: error early if yaml_file or output_folder are not set

    # Parse YAML file
    with open(yaml_file, "r") as file:
        data = yaml.safe_load(file)

    # Create QTI 1.2 XML structure
    main_element = Element(
        "questestinterop",
        nsmap={
            None: "http://www.imsglobal.org/xsd/imsqti_v2p1",
            "xsi": "http://www.w3.org/2001/XMLSchema-instance",
        },
    )
    # have to set schemaLocation like this for some reason
    main_element.set(
        "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation",
        "http://www.imsglobal.org/xsd/imsqti_v2p1 http://www.imsglobal.org/xsd/imsqti_v2p1p1.xsd",
    )
    questestinterop = ElementTree(main_element)

    bank_title = "Question bank"
    if "bank_info" in data:
        if "title" in data["bank_info"]:
            bank_title = data["bank_info"]["title"]
        if "bank_id" in data["bank_info"]:
            bank_id = data["bank_info"]["bank_id"] + " "

    assessment = SubElement(
        questestinterop.getroot(), "assessment", ident="qti", title=bank_id + bank_title
    )
    qtimetadata = SubElement(assessment, "qtimetadata")
    qtimemetadatafield = SubElement(qtimetadata, "qtimetadatafield")
    SubElement(qtimemetadatafield, "fieldlabel").text = "cc_maxattempts"
    SubElement(qtimemetadatafield, "fieldentry").text = "1"

    section = SubElement(assessment, "section", ident="root_section")

    # handle files that lack all other contextual data and just list questions
    all_questions = []
    if "bank_info" not in data and "questions" not in data and isinstance(data, list):
        all_questions = data
    elif "questions" in data:
        all_questions = data.get("questions", [])
    else:
        raise Exception(
            "Provided YAML file is not properly formatted, 'questions' object is missing."
        )

    for question in all_questions:
        # this seems a bit roundabout - potentially adjust the generation process to indicate
        #  'multiple_choice', 'numerical' etc. as a property of each question rather than the top
        #  level attribute?
        question_type = list(question.keys())[0]
        question_obj = question[question_type]

        xml_element = standard_question_start(section, question_type, question_obj)

        if question_type == "multiple_choice":
            xml_element = convert_multiple_choice_to_qti(
                xml_element, question_obj, shuffle_mult
            )
        elif question_type == "numerical":
            xml_element = convert_numerical_to_qti(xml_element, question_obj)
        elif question_type == "true_false":
            xml_element = convert_true_false_to_qti(xml_element, question_obj)
        elif question_type == "categorization":
            xml_element = convert_categorization_to_qti(xml_element, question_obj)
        elif question_type == "essay":
            xml_element = convert_essay_to_qti(xml_element, question_obj)
        elif question_type == "file_upload":
            xml_element = convert_file_upload_to_qti(xml_element, question_obj)
        elif question_type == "ordering":
            xml_element = convert_ordering_to_qti(xml_element, question_obj)
        elif question_type == "fill_in_multiple_blanks":
            xml_element = convert_fill_in_the_blank_to_qti(xml_element, question_obj)
        elif question_type == "formula":
            xml_element = convert_formula_to_qti(xml_element, question_obj)
        elif question_type == "multiple_answers":
            xml_element = convert_multiple_answer_to_qti(
                xml_element, question_obj, shuffle_mult
            )
        elif question_type == "hot_spot":
            xml_element = convert_hotspot_to_qti(xml_element, question_obj)
        elif question_type == "matching":
            xml_element = convert_matching_to_qti(xml_element, question_obj)
        else:
            raise Exception(f"Unsupported question type {question_type}")

        # build feedback when applicable
        if "feedback" in question_obj:
            feedback_obj = question_obj["feedback"]
            if "general" in feedback_obj:
                create_feedback_tree(xml_element, "general_fb", feedback_obj["general"])
            if "on_correct" in feedback_obj:
                create_feedback_tree(
                    xml_element, "correct_fb", feedback_obj["on_correct"]
                )
            if "on_incorrect" in feedback_obj:
                create_feedback_tree(
                    xml_element, "general_incorrect_fb", feedback_obj["on_incorrect"]
                )

        # check to make sure any media in the question actually exists
        if "figure" in question_obj:
            figure_path_parts = question_obj["figure"].split("/")
            filename = figure_path_parts[-1]
            if not os.path.isfile(os.path.join(output_folder, "media", filename)):
                raise Exception(f"File '{filename}' is missing from provided media.")

    pretty_xml = tostring(
        questestinterop.getroot(),
        pretty_print=True,
        encoding="utf-8",
        xml_declaration=True,
    )
    output_file = os.path.join(output_folder, "qti", "qti.xml")
    with open(output_file, "wb") as file:
        file.write(pretty_xml)


if __name__ == "__main__":
    yaml_file = input("Enter the path to the YAML file: ").strip()
    output_folder = input("Enter the path for the output folder: ").strip()

    yaml_to_qti(yaml_file, output_folder)
    output_file = os.path.join(output_folder, "qti", "qti.xml")
    print(f"QTI 1.2 XML file created: {output_file}")
