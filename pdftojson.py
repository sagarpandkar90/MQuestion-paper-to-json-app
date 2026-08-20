"""
==========================================================
MPSC Question Paper Ingestion & Editor Tool (Gemini AI Powered)
Version : 19.0 (Null-Language Fields + Resumable Continuation Extraction)
Author  : Tejas Doiphode

Features
---------
✓ 20 Quantitative Aptitude micro-topics added directly from Image Index (Subject ID: 17)
✓ 37 Intelligence/Reasoning micro-topics added directly from Image Index (Subject ID: 18)
✓ 2 Logical Reasoning & Decision Making micro-topics added directly from Image Index (Subject ID: 19)
✓ All previous Polity (19), History (26), Geography (28), Science (29), Economics (16) topics maintained
✓ Concurrent Dual-PDF Processing: Upload Question Paper PDF & Answer Key PDF together
✓ NEW: If a question exists in the source PDF in only ONE language, that
  language is extracted as-is and the OTHER language is set to null in the
  JSON (no fabricated translation). If both languages are present in the
  source, both are extracted as "English Text [[MR]] मराठी मजकूर".
✓ NEW: Resumable / continuation extraction — if a run only returns a partial
  set of questions (e.g. 30 of 100, due to model output limits), you can
  upload that partial JSON back in and continue extraction from the next
  question number using the same paper PDF, appending results until the
  full paper is covered.
✓ Auto-assigns correct_option directly from Answer Key PDF via Gemini AI
✓ Safe NoneType handling for null options/strings
==========================================================
"""

import json
import os
import re
import tempfile
from datetime import datetime

import streamlit as st

# Modern Google GenAI SDK import
try:
    from google import genai
    from google.genai import types
except ImportError:
    st.error("Please install the new Google GenAI library: pip install google-genai")

# --------------------------------------------------------
# 1. Page Config & Micro-Level Syllabus Definition
# --------------------------------------------------------

st.set_page_config(
    page_title="MPSC प्रश्नपत्रिका संकलन व संपादक टूल",
    page_icon="🤖",
    layout="wide"
)

st.title("🤖 MPSC प्रश्नपत्रिका संकलन व स्मार्ट JSON जनरेटर")
st.caption("भाषा-निष्ठ (Language-Faithful) PDF प्रक्रिया, ऑटो-वर्गीकरण, टप्प्याटप्प्याने (Resumable) संकलन व संपादक टूल")

MARATHI_SUBJECTS = [
    {"id": 1, "name": "राज्यघटना व राज्यव्यवस्था", "description": "भारतीय संविधान, राज्यव्यवस्था, न्यायव्यवस्था व हक्क", "color_hex": "#2980B9", "icon": "gavel", "order": 1},
    {"id": 2, "name": "पंचायतराज", "description": "स्थानिक स्वराज्य संस्था, ७३ वी व ७४ वी घटनादुरुस्ती", "color_hex": "#16A085", "icon": "account_balance", "order": 2},
    {"id": 3, "name": "प्राचीन इतिहास", "description": "प्राचीन भारत - सिंधू, वैदिक, मौर्य, गुप्त कालखंड", "color_hex": "#D35400", "icon": "history", "order": 3},
    {"id": 4, "name": "मध्ययुगीन इतिहास", "description": "मध्ययुगीन भारत - सुलतानशाही, मुघल, भक्ति चळवळ", "color_hex": "#E67E22", "icon": "castle", "order": 4},
    {"id": 5, "name": "आधुनिक भारताचा इतिहास", "description": "ब्रिटिश सत्ता, १८५७ चा उठाव व स्वातंत्र्य लढा", "color_hex": "#C0392B", "icon": "history_edu", "order": 5},
    {"id": 6, "name": "महाराष्ट्राचा इतिहास व समाजसुधारक", "description": "महाराष्ट्रातील इतिहास, उठाव, लढा व समाजसुधारक", "color_hex": "#E74C3C", "icon": "person", "order": 6},
    {"id": 7, "name": "जगाचा व प्राकृतिक भूगोल", "description": "प्राकृतिक भूगोल, हवामानशास्त्र व भूरूपे", "color_hex": "#27AE60", "icon": "public", "order": 7},
    {"id": 8, "name": "भारताचा भूगोल", "description": "भारताची प्राकृतिक रचना, नद्या, खनिजे व लोकसंख्या", "color_hex": "#2ECC71", "icon": "map", "order": 8},
    {"id": 9, "name": "महाराष्ट्राचा भूगोल", "description": "महाराष्ट्राची प्राकृतिक रचना, नद्या, खनिजे व प्रशासकीय विभाग", "color_hex": "#1ABC9C", "icon": "place", "order": 9},
    {"id": 10, "name": "पर्यावरण व परिस्थितीकी", "description": "पारिस्थितीकी, जैवविविधता व हवामान बदल", "color_hex": "#16A085", "icon": "eco", "order": 10},
    {"id": 11, "name": "अर्थशास्त्र व विकास", "description": "राष्ट्रीय उत्पन्न, बँकिंग, सार्वजनिक वित्त व नियोजन", "color_hex": "#8E44AD", "icon": "currency_rupee", "order": 11},
    {"id": 12, "name": "आरोग्यशास्त्र व मानवी शरीरशास्त्र", "description": "पोषक द्रव्ये, मानवी शरीर संस्था व रोग", "color_hex": "#E91E63", "icon": "medical_services", "order": 12},
    {"id": 13, "name": "जीवशास्त्र", "description": "पेशीशास्त्र, उतीशास्त्र, प्राणी व वनस्पती वर्गीकरण", "color_hex": "#9C27B0", "icon": "biotech", "order": 13},
    {"id": 14, "name": "भौतिक शास्त्र", "description": "गती, बल, प्रकाश, ध्वनी, उष्णता व विद्युत", "color_hex": "#3F51B5", "icon": "bolt", "order": 14},
    {"id": 15, "name": "रसायन शास्त्र", "description": "अणू रचना, आवर्तसारणी, आम्ल-आम्लारी व धातू", "color_hex": "#00BCD4", "icon": "science", "order": 15},
    {"id": 16, "name": "विज्ञान व तंत्रज्ञान", "description": "ऊर्जा, अंतराळ, माहिती तंत्रज्ञान व आपत्ती व्यवस्थापन", "color_hex": "#009688", "icon": "memory", "order": 16},
    {"id": 17, "name": "अंकगणित", "description": "संख्या, सरासरी, टक्केवारी, नफा-तोटा, काळ-काम-वेग", "color_hex": "#FF9800", "icon": "calculate", "order": 17},
    {"id": 18, "name": "बुद्धिमत्ता चाचणी", "description": "मालिका, सांकेतिक भाषा, नातेसंबंध, कूटप्रश्न व आकृत्या", "color_hex": "#FF5722", "icon": "psychology", "order": 18},
    {"id": 19, "name": "तार्किक व निर्णय क्षमता", "description": "तार्किक युक्तिवाद व निर्णय क्षमता", "color_hex": "#795548", "icon": "balance", "order": 19},
    {"id": 20, "name": "मराठी भाषा व व्याकरण", "description": "मराठी व्याकरण, शब्दसिद्धी, शुद्धलेखन व शब्दसंग्रह", "color_hex": "#607D8B", "icon": "translate", "order": 20},
    {"id": 21, "name": "इंग्रजी भाषा व व्याकरण (English Language)", "description": "English Grammar, Vocabulary & Passages", "color_hex": "#34495E", "icon": "language", "order": 21},
    {"id": 22, "name": "चालू घडामोडी", "description": "राज्य, राष्ट्रीय व जागतिक महत्वाच्या घडामोडी", "color_hex": "#F39C12", "icon": "newspaper", "order": 22}
]

MARATHI_TOPICS = [
    {"id": 101, "subject_id": 1, "name": "०१. घटना निर्मिती व घटनेची वैशिष्ट्ये", "description": "", "order": 1},
    {"id": 102, "subject_id": 1, "name": "०२. प्रस्तावना / उद्देशपत्रिका / नांदी", "description": "", "order": 2},
    {"id": 103, "subject_id": 1, "name": "०३. संघराज्य व राज्यक्षेत्र", "description": "", "order": 3},
    {"id": 104, "subject_id": 1, "name": "०४. नागरिकत्व", "description": "", "order": 4},
    {"id": 105, "subject_id": 1, "name": "०५. मुलभूत हक्क", "description": "", "order": 5},
    {"id": 106, "subject_id": 1, "name": "०६. मार्गदर्शक तत्त्वे, मुलभूत कर्तव्ये", "description": "", "order": 6},
    {"id": 107, "subject_id": 1, "name": "०७. घटनादुरुस्ती पद्धत व घटना दुरुस्त्या", "description": "", "order": 7},
    {"id": 108, "subject_id": 1, "name": "०८. राष्ट्रपती व उपराष्ट्रपती", "description": "", "order": 8},
    {"id": 109, "subject_id": 1, "name": "०९. पंतप्रधान व मंत्रिमंडळ", "description": "", "order": 9},
    {"id": 110, "subject_id": 1, "name": "१०. संसद", "description": "", "order": 10},
    {"id": 111, "subject_id": 1, "name": "११. विधानमंडळ", "description": "", "order": 11},
    {"id": 112, "subject_id": 1, "name": "१२. न्यायमंडळ", "description": "", "order": 12},
    {"id": 113, "subject_id": 1, "name": "१३. घटनात्मक / बिगर घटनात्मक आयोग", "description": "", "order": 13},
    {"id": 114, "subject_id": 1, "name": "१४. आणीबाणी", "description": "", "order": 14},
    {"id": 115, "subject_id": 1, "name": "१५. केंद्रशासित प्रदेश", "description": "", "order": 15},
    {"id": 116, "subject_id": 1, "name": "१६. केंद्र-राज्य संबंध", "description": "", "order": 16},
    {"id": 117, "subject_id": 1, "name": "१७. ग्रामप्रशासन", "description": "", "order": 17},
    {"id": 118, "subject_id": 1, "name": "१८. महान्यायवादी व महाधिवक्ता", "description": "", "order": 18},
    {"id": 119, "subject_id": 1, "name": "१९. अनुसूची / सूची / भाग / कलमे / खटले", "description": "", "order": 19},
    {"id": 201, "subject_id": 2, "name": "पंचायत राज उत्क्रांती, ७३वी व ७४वी घटनादुरुस्ती", "description": "", "order": 1},
    {"id": 202, "subject_id": 2, "name": "ग्रामिण व नागरी स्थानिक स्वराज्य संस्था", "description": "", "order": 2},
    {"id": 301, "subject_id": 3, "name": "प्राचीन भारत (सिंधू, वैदिक, मौर्य व गुप्त साम्राज्य)", "description": "", "order": 1},
    {"id": 401, "subject_id": 4, "name": "मध्ययुगीन भारत (सुलतानशाही, मुघल साम्राज्य व भक्ति चळवळ)", "description": "", "order": 1},
    {"id": 501, "subject_id": 5, "name": "०१. कायदे (1773-1935)", "description": "", "order": 1},
    {"id": 502, "subject_id": 5, "name": "०२. भू-सुधारणा : रयतवारी, महालवारी, कायमधारा", "description": "", "order": 2},
    {"id": 503, "subject_id": 5, "name": "०३. गव्हर्नर जनरलस् व व्हाईसरॉय (1773-1947)", "description": "", "order": 3},
    {"id": 504, "subject_id": 5, "name": "०४. ब्रिटिशांचे धोरण : सामाजिक, आर्थिक, प्रशासकीय", "description": "", "order": 4},
    {"id": 505, "subject_id": 5, "name": "०५. 1857 चा उठाव व परिणाम", "description": "", "order": 5},
    {"id": 506, "subject_id": 5, "name": "०६. भारतातील शिक्षणाची वृद्धी व विकास", "description": "", "order": 6},
    {"id": 507, "subject_id": 5, "name": "०७. भारतातील वृत्तपत्राचा इतिहास", "description": "", "order": 7},
    {"id": 508, "subject_id": 5, "name": "०८. सुधारणा चळवळी : सामाजिक, धार्मिक, सांस्कृतिक", "description": "", "order": 8},
    {"id": 509, "subject_id": 5, "name": "०९. काँग्रेसपूर्व संघटना", "description": "", "order": 9},
    {"id": 510, "subject_id": 5, "name": "१०. काँग्रेसची स्थापना व अधिवेशने", "description": "", "order": 10},
    {"id": 511, "subject_id": 5, "name": "११. मवाळ कालखंड (1885 ते 1905)", "description": "", "order": 11},
    {"id": 512, "subject_id": 5, "name": "१२. जहाल कालखंड (1905 ते 1920)", "description": "", "order": 12},
    {"id": 513, "subject_id": 5, "name": "१३. बंगालची फाळणी व वंगभंग चळवळ", "description": "", "order": 13},
    {"id": 514, "subject_id": 5, "name": "१४. मुस्लिम लीग", "description": "", "order": 14},
    {"id": 515, "subject_id": 5, "name": "१५. गदर व होमरूल चळवळ", "description": "", "order": 15},
    {"id": 516, "subject_id": 5, "name": "१६. सत्याग्रह : चंपारण्य, अहमदाबाद, खेडा, रौलेट, हंटर कमिशन, बारडोली", "description": "", "order": 16},
    {"id": 517, "subject_id": 5, "name": "१७. असहकार व खिलाफत चळवळ", "description": "", "order": 17},
    {"id": 518, "subject_id": 5, "name": "१८. स्वराज्य पार्टीची कामगिरी", "description": "", "order": 18},
    {"id": 519, "subject_id": 5, "name": "१९. सविनय कायदेभंग (1930-34)", "description": "", "order": 19},
    {"id": 520, "subject_id": 5, "name": "२०. सायमन कमिशन, नेह्रू अहवाल", "description": "", "order": 20},
    {"id": 521, "subject_id": 5, "name": "२१. राष्ट्रीय चळवळ", "description": "", "order": 21},
    {"id": 522, "subject_id": 5, "name": "२२. चलेजाव आंदोलन, 1942", "description": "", "order": 22},
    {"id": 523, "subject_id": 5, "name": "२३. क्रांतिकारी चळवळ व सुभाषचंद्र बोस", "description": "", "order": 23},
    {"id": 524, "subject_id": 5, "name": "२४. राष्ट्रीय चळवळ (1945 ते 1947)", "description": "", "order": 24},
    {"id": 525, "subject_id": 5, "name": "२५. डावी चळवळ", "description": "", "order": 25},
    {"id": 526, "subject_id": 5, "name": "२६. आदिवासी, शेतकरी, कामगार यांच्या चळवळी", "description": "", "order": 26},
    {"id": 601, "subject_id": 6, "name": "०१. 1857 पूर्वीचे उठाव", "description": "", "order": 1},
    {"id": 602, "subject_id": 6, "name": "०२. 1857 चा उठाव व महाराष्ट्र", "description": "", "order": 2},
    {"id": 603, "subject_id": 6, "name": "०३. काँग्रेसपूर्व राजकीय संघटना", "description": "", "order": 3},
    {"id": 604, "subject_id": 6, "name": "०४. महाराष्ट्रातील असहकार चळवळ", "description": "", "order": 4},
    {"id": 605, "subject_id": 6, "name": "०५. महाराष्ट्रातील सविनय कायदेभंग चळवळ", "description": "", "order": 5},
    {"id": 606, "subject_id": 6, "name": "०६. राष्ट्रीय चळवळ व महाराष्ट्र", "description": "", "order": 6},
    {"id": 607, "subject_id": 6, "name": "०७. क्रांतिकारी चळवळ", "description": "", "order": 7},
    {"id": 608, "subject_id": 6, "name": "०८. सामाजिक व धार्मिक सुधारणा चळवळी", "description": "", "order": 8},
    {"id": 609, "subject_id": 6, "name": "०९. कामगार चळवळ", "description": "", "order": 9},
    {"id": 610, "subject_id": 6, "name": "१०. दलित व ब्राह्मणेत्तर चळवळ", "description": "", "order": 10},
    {"id": 611, "subject_id": 6, "name": "११. आदिवासी व शेतकरी चळवळ", "description": "", "order": 11},
    {"id": 612, "subject_id": 6, "name": "१२. संयुक्त महाराष्ट्र चळवळ", "description": "", "order": 12},
    {"id": 613, "subject_id": 6, "name": "१३. मराठवाडा मुक्तीसंग्राम", "description": "", "order": 13},
    {"id": 614, "subject_id": 6, "name": "१४. महाराष्ट्राचा विकास (1960-2021)", "description": "", "order": 14},
    {"id": 615, "subject_id": 6, "name": "१५. महाराष्ट्रातील वृत्तपत्रे", "description": "", "order": 15},
    {"id": 616, "subject_id": 6, "name": "१६. महाराष्ट्रातील समाजसुधारक", "description": "", "order": 16},
    {"id": 801, "subject_id": 8, "name": "०१. भारत : स्थान, विस्तार व आकार", "description": "", "order": 1},
    {"id": 802, "subject_id": 8, "name": "०२. भारताचे प्राकृतिक विभाग", "description": "", "order": 2},
    {"id": 803, "subject_id": 8, "name": "०३. भूशास्त्र (भूगर्भरचना)", "description": "", "order": 3},
    {"id": 804, "subject_id": 8, "name": "०४. भारतीय बेटे (अंदमान, निकोबार व लक्षद्वीप)", "description": "", "order": 4},
    {"id": 805, "subject_id": 8, "name": "०५. वनसंपदा", "description": "", "order": 5},
    {"id": 806, "subject_id": 8, "name": "०६. हवामान : पर्जन्य व वारे", "description": "", "order": 6},
    {"id": 807, "subject_id": 8, "name": "०७. मृदा", "description": "", "order": 7},
    {"id": 808, "subject_id": 8, "name": "०८. कृषी", "description": "", "order": 8},
    {"id": 809, "subject_id": 8, "name": "०९. खनिज संपत्ती", "description": "", "order": 9},
    {"id": 810, "subject_id": 8, "name": "१०. ऊर्जा साधने", "description": "", "order": 10},
    {"id": 811, "subject_id": 8, "name": "११. उद्योगधंदे", "description": "", "order": 11},
    {"id": 812, "subject_id": 8, "name": "१२. वाहतूक व पर्यटन", "description": "", "order": 12},
    {"id": 813, "subject_id": 8, "name": "१३. लोकसंख्या, जमाती", "description": "", "order": 13},
    {"id": 814, "subject_id": 8, "name": "१४. स्थलांतर", "description": "", "order": 14},
    {"id": 815, "subject_id": 8, "name": "१५. भारतातील राज्ये/केंद्रशासित प्रदेश", "description": "", "order": 15},
    {"id": 816, "subject_id": 8, "name": "१६. नदीप्रणाली", "description": "", "order": 16},
    {"id": 901, "subject_id": 9, "name": "०१. महाराष्ट्र : स्थान, विस्तार व आकार", "description": "", "order": 1},
    {"id": 902, "subject_id": 9, "name": "०२. महाराष्ट्राचा प्राकृतिक भूगोल", "description": "", "order": 2},
    {"id": 903, "subject_id": 9, "name": "०३. नदी प्रणाली", "description": "", "order": 3},
    {"id": 904, "subject_id": 9, "name": "०४. हवामान (पर्जन्य, वारे, मान्सून)", "description": "", "order": 4},
    {"id": 905, "subject_id": 9, "name": "०५. वने (अभयारण्य, राष्ट्रीय उद्याने व व्याघ्र प्रकल्प)", "description": "", "order": 5},
    {"id": 906, "subject_id": 9, "name": "०६. खनिज संपत्ती", "description": "", "order": 6},
    {"id": 907, "subject_id": 9, "name": "०७. लोकसंख्या (धोरणे, टप्पे, इतर सर्वच)", "description": "", "order": 7},
    {"id": 908, "subject_id": 9, "name": "०८. स्थलांतर", "description": "", "order": 8},
    {"id": 909, "subject_id": 9, "name": "०९. मृदा व जलसिंचन", "description": "", "order": 9},
    {"id": 910, "subject_id": 9, "name": "१०. वाहतूक व पर्यटन स्थळे", "description": "", "order": 10},
    {"id": 911, "subject_id": 9, "name": "११. इतर", "description": "", "order": 11},
    {"id": 912, "subject_id": 9, "name": "१२. आर्थिक भूगोल", "description": "", "order": 12},
    {"id": 1001, "subject_id": 10, "name": "पर्यावरण परिस्थितीकी, जैवविविधता व हवामान बदल", "description": "", "order": 1},
    {"id": 1101, "subject_id": 11, "name": "०१. भारतीय अर्थव्यवस्था", "description": "", "order": 1},
    {"id": 1102, "subject_id": 11, "name": "०२. राष्ट्रीय उत्पन्न", "description": "", "order": 2},
    {"id": 1103, "subject_id": 11, "name": "०३. मानव विकास अहवाल (HDR)", "description": "", "order": 3},
    {"id": 1104, "subject_id": 11, "name": "०४. आर्थिक नियोजन व पंचवार्षिक योजना", "description": "", "order": 4},
    {"id": 1105, "subject_id": 11, "name": "०५. योजना / धोरण / कार्यक्रम / समिती", "description": "", "order": 5},
    {"id": 1106, "subject_id": 11, "name": "०६. दारिद्र्य व बेरोजगारी", "description": "", "order": 6},
    {"id": 1107, "subject_id": 11, "name": "०७. लोकसंख्या (भूगोलमधील पण हा घटक वाचा)", "description": "", "order": 7},
    {"id": 1108, "subject_id": 11, "name": "०८. बँकिंग (RBI सह)", "description": "", "order": 8},
    {"id": 1109, "subject_id": 11, "name": "०९. भारताचा आंतरराष्ट्रीय व्यापार", "description": "", "order": 9},
    {"id": 1110, "subject_id": 11, "name": "१०. सार्वजनिक वित्त व कर संरचना", "description": "", "order": 10},
    {"id": 1111, "subject_id": 11, "name": "११. कृषी, उद्योग व सेवा क्षेत्र", "description": "", "order": 11},
    {"id": 1112, "subject_id": 11, "name": "१२. आर्थिक सुधारणा", "description": "", "order": 12},
    {"id": 1113, "subject_id": 11, "name": "१३. पायाभूत सुविधा", "description": "", "order": 13},
    {"id": 1114, "subject_id": 11, "name": "१४. आंतरराष्ट्रीय वित्तीय संघटना", "description": "", "order": 14},
    {"id": 1115, "subject_id": 11, "name": "१५. अर्थसंकल्पावर आधारित प्रश्न", "description": "", "order": 15},
    {"id": 1116, "subject_id": 11, "name": "१६. भारतीय अर्थव्यवस्थेशी संबंधित इतर चालू घडामोडी", "description": "", "order": 16},
    {"id": 1201, "subject_id": 12, "name": "०९. मानवातील ग्रंथी, संप्रेरके व विकरे (Glands, Hormones & Enzymes)", "description": "", "order": 1},
    {"id": 1202, "subject_id": 12, "name": "१०. प्रजनन संस्था (Reproduction System)", "description": "", "order": 2},
    {"id": 1203, "subject_id": 12, "name": "११. अस्थी संस्था (Skeletal System)", "description": "", "order": 3},
    {"id": 1204, "subject_id": 12, "name": "१२. ऊती (Tissue)", "description": "", "order": 4},
    {"id": 1205, "subject_id": 12, "name": "१३. पोषण (Nutrition)", "description": "", "order": 5},
    {"id": 1206, "subject_id": 12, "name": "१४. रोग (Disease)", "description": "", "order": 6},
    {"id": 1207, "subject_id": 12, "name": "१५. जैवतंत्रज्ञान (Biotechnology)", "description": "", "order": 7},
    {"id": 1208, "subject_id": 12, "name": "१६. वनस्पतींचे पोषण (Plant Nutrition)", "description": "", "order": 8},
    {"id": 1209, "subject_id": 12, "name": "१७. वनस्पतींवरील रोग (Diseases of Plants)", "description": "", "order": 9},
    {"id": 1210, "subject_id": 12, "name": "१८. कृषी (Agriculture)", "description": "", "order": 10},
    {"id": 1301, "subject_id": 13, "name": "०१. पेशी (Cell)", "description": "", "order": 1},
    {"id": 1302, "subject_id": 13, "name": "०२. सजीवांच्या वर्गीकरणाच्या पद्धती (Method of classification of plants)", "description": "", "order": 2},
    {"id": 1303, "subject_id": 13, "name": "०३. मोनेरा, प्रोटीस्टा व कवकांचे वर्गीकरण (Classification of Monera, Protista & Fungi)", "description": "", "order": 3},
    {"id": 1304, "subject_id": 13, "name": "०४. वनस्पतींचे वर्गीकरण (Plant Classification)", "description": "", "order": 4},
    {"id": 1305, "subject_id": 13, "name": "०५. प्राण्यांचे वर्गीकरण (Animal Classification)", "description": "", "order": 5},
    {"id": 1306, "subject_id": 13, "name": "०६. मानवी रक्ताभिसरण संस्था (Human Circulatory System)", "description": "", "order": 6},
    {"id": 1307, "subject_id": 13, "name": "०७. मानवी श्वसन संस्था (Human Respiratory System)", "description": "", "order": 7},
    {"id": 1308, "subject_id": 13, "name": "०८. उत्सर्जन संस्था (Excretory System)", "description": "", "order": 8},
    {"id": 1401, "subject_id": 14, "name": "०१. भौतिक राशींचे मापन व एकके (Measurement of Physical Quantities & Units)", "description": "", "order": 1},
    {"id": 1402, "subject_id": 14, "name": "०२. गती, बल व चाल (Velocity, Force, Speed)", "description": "", "order": 2},
    {"id": 1403, "subject_id": 14, "name": "०३. कार्य, ऊर्जा आणि शक्ती (Work, Energy & Power)", "description": "", "order": 3},
    {"id": 1404, "subject_id": 14, "name": "०४. गुरुत्वाकर्षण बल (Gravitational Force)", "description": "", "order": 4},
    {"id": 1405, "subject_id": 14, "name": "०५. ध्वनी (Sound)", "description": "", "order": 5},
    {"id": 1406, "subject_id": 14, "name": "०६. प्रकाश (Light)", "description": "", "order": 6},
    {"id": 1407, "subject_id": 14, "name": "०७. विद्युतधारा (Electricity)", "description": "", "order": 7},
    {"id": 1408, "subject_id": 14, "name": "०८. चुंबकत्व व विद्युत चुंबकीय पट्टा (Magnetism & Spectrum)", "description": "", "order": 8},
    {"id": 1409, "subject_id": 14, "name": "०९. किरणोत्सारीता (Radioactivity)", "description": "", "order": 9},
    {"id": 1410, "subject_id": 14, "name": "१०. खगोलशास्त्र (Space Science)", "description": "", "order": 10},
    {"id": 1411, "subject_id": 14, "name": "११. चालू घडामोडी", "description": "", "order": 11},
    {"id": 1501, "subject_id": 15, "name": "०१. द्रव आणि त्याचे स्वरूप (States of Matter and It's Nature)", "description": "", "order": 1},
    {"id": 1502, "subject_id": 15, "name": "०२. अणूंची संरचना (Atomic Structure)", "description": "", "order": 2},
    {"id": 1503, "subject_id": 15, "name": "०३. आवर्त सारणी (Periodic Table)", "description": "", "order": 3},
    {"id": 1504, "subject_id": 15, "name": "०४. मुलद्रव्यांचे वर्गीकरण (Classification of Elements)", "description": "", "order": 4},
    {"id": 1505, "subject_id": 15, "name": "०५. खनिजे आणि धातूके (Minerals and Ores)", "description": "", "order": 5},
    {"id": 1506, "subject_id": 15, "name": "०६. रासायनिक अभिक्रिया (Chemical Reactions)", "description": "", "order": 6},
    {"id": 1507, "subject_id": 15, "name": "०७. आम्ल व आम्लारी (Acids and Bases)", "description": "", "order": 7},
    {"id": 1508, "subject_id": 15, "name": "०८. कार्बनचे जग (Organic Chemistry)", "description": "", "order": 8},
    {"id": 1509, "subject_id": 15, "name": "०९. संकिर्ण रसायन शास्त्र (Miscellaneous Chemistry)", "description": "", "order": 9},
    {"id": 1510, "subject_id": 15, "name": "१०. पर्यावरण (Environment)", "description": "", "order": 10},
    {"id": 1601, "subject_id": 16, "name": "विज्ञान तंत्रज्ञान - ऊर्जा, अंतराळ, ICT व आपत्ती व्यवस्थापन", "description": "", "order": 1},
    {"id": 1701, "subject_id": 17, "name": "०१. संख्या", "description": "", "order": 1},
    {"id": 1702, "subject_id": 17, "name": "०२. अपूर्णांक", "description": "", "order": 2},
    {"id": 1703, "subject_id": 17, "name": "०३. वर्गमूळ, घातांक", "description": "", "order": 3},
    {"id": 1704, "subject_id": 17, "name": "०४. सरासरी", "description": "", "order": 4},
    {"id": 1705, "subject_id": 17, "name": "०५. विभाज्यता", "description": "", "order": 5},
    {"id": 1706, "subject_id": 17, "name": "०६. लसावि व मसावि", "description": "", "order": 6},
    {"id": 1707, "subject_id": 17, "name": "०७. समिकरणे", "description": "", "order": 7},
    {"id": 1708, "subject_id": 17, "name": "०८. पदावली", "description": "", "order": 8},
    {"id": 1709, "subject_id": 17, "name": "०९. शेकडेवारी", "description": "", "order": 9},
    {"id": 1710, "subject_id": 17, "name": "१०. नफा-तोटा सुट", "description": "", "order": 10},
    {"id": 1711, "subject_id": 17, "name": "११. व्याज", "description": "", "order": 11},
    {"id": 1712, "subject_id": 17, "name": "१२. गुणोत्तर व प्रमाण", "description": "", "order": 12},
    {"id": 1713, "subject_id": 17, "name": "१३. भागीदारी व मिश्रण", "description": "", "order": 13},
    {"id": 1714, "subject_id": 17, "name": "१४. श्रेणी", "description": "", "order": 14},
    {"id": 1715, "subject_id": 17, "name": "१५. काळ-काम, नळ व टाकी", "description": "", "order": 15},
    {"id": 1716, "subject_id": 17, "name": "१६. वेळ, वेग, अंतर", "description": "", "order": 16},
    {"id": 1717, "subject_id": 17, "name": "१७. भूमितीय संकल्पना", "description": "", "order": 17},
    {"id": 1718, "subject_id": 17, "name": "१८. संयोजन", "description": "", "order": 18},
    {"id": 1719, "subject_id": 17, "name": "१९. गणितीय क्रिया", "description": "", "order": 19},
    {"id": 1720, "subject_id": 17, "name": "२०. संकीर्ण", "description": "", "order": 20},
    {"id": 1801, "subject_id": 18, "name": "०१. अंकमालिका (Number Series)", "description": "", "order": 1},
    {"id": 1802, "subject_id": 18, "name": "०२. संख्या शोध (Missing Number)", "description": "", "order": 2},
    {"id": 1803, "subject_id": 18, "name": "०३. वर्णमालिका (Alphabetical Series)", "description": "", "order": 3},
    {"id": 1804, "subject_id": 18, "name": "०४. सहसंबंध - अंक : अंक (Analogy)", "description": "", "order": 4},
    {"id": 1805, "subject_id": 18, "name": "०५. सहसंबंध - अक्षर - अक्षर (Analogy)", "description": "", "order": 5},
    {"id": 1806, "subject_id": 18, "name": "०६. सहसंबंध - शब्द - शब्द (Word Analogy)", "description": "", "order": 6},
    {"id": 1807, "subject_id": 18, "name": "०७. विसंगत घटक (Odd Man Out) संख्या", "description": "", "order": 7},
    {"id": 1808, "subject_id": 18, "name": "०८. विसंगत घटक-अक्षर गट (Odd ManOut) संख्या", "description": "", "order": 8},
    {"id": 1809, "subject_id": 18, "name": "०९. सांकेतिक भाषा-अक्षर अंक (Coding-Decoding)", "description": "", "order": 9},
    {"id": 1810, "subject_id": 18, "name": "१०. सांकेतिक भाषा-अक्षर चिन्हे (Coding-Decoding)", "description": "", "order": 10},
    {"id": 1811, "subject_id": 18, "name": "११. सांकेतिक भाषा-गणित (Coding-Decoding-Math)", "description": "", "order": 11},
    {"id": 1812, "subject_id": 18, "name": "१२. सांकेतिक भाषा-विशेष (Coding-Decoding-Special Case)", "description": "", "order": 12},
    {"id": 1813, "subject_id": 18, "name": "१३. वयवारी (Ages)", "description": "", "order": 13},
    {"id": 1814, "subject_id": 18, "name": "१४. दिशा (Direction)", "description": "", "order": 14},
    {"id": 1815, "subject_id": 18, "name": "१५. घड्याळ (Clock)", "description": "", "order": 15},
    {"id": 1816, "subject_id": 18, "name": "१६. दिनदर्शिका (Calendar)", "description": "", "order": 16},
    {"id": 1817, "subject_id": 18, "name": "१७. रांग (Rows)", "description": "", "order": 17},
    {"id": 1818, "subject_id": 18, "name": "१८. नाते संबंध (Blood Relation)", "description": "", "order": 18},
    {"id": 1819, "subject_id": 18, "name": "१९. विधाने-गृहीतके, निष्कर्ष (Statements-Assumptions,Conclusion)", "description": "", "order": 19},
    {"id": 1820, "subject_id": 18, "name": "२०. कूटप्रश्न (Puzzle)", "description": "", "order": 20},
    {"id": 1821, "subject_id": 18, "name": "२१. सांकेतिक तुलना (Coded Comparison)", "description": "", "order": 21},
    {"id": 1822, "subject_id": 18, "name": "२२. व्यवस्था (Arrangements)", "description": "", "order": 22},
    {"id": 1823, "subject_id": 18, "name": "२३. शब्द (Words)", "description": "", "order": 23},
    {"id": 1824, "subject_id": 18, "name": "२४. चिन्हाचे अर्थ (Symbol Meaning)", "description": "", "order": 24},
    {"id": 1825, "subject_id": 18, "name": "२५. संकीर्ण (Others)", "description": "", "order": 25},
    {"id": 1826, "subject_id": 18, "name": "२६. वेन आकृती (Diagrammes)", "description": "", "order": 26},
    {"id": 1827, "subject_id": 18, "name": "२७. घन आणि वेन आकृती (Diagrammes)", "description": "", "order": 27},
    {"id": 1828, "subject_id": 18, "name": "२८. आकृती शृंखला (Diagrammes)", "description": "", "order": 28},
    {"id": 1829, "subject_id": 18, "name": "२९. आकृती अक्षरे (Image Words)", "description": "", "order": 29},
    {"id": 1830, "subject_id": 18, "name": "३०. आकृती सहसंबंध (Image Analogy)", "description": "", "order": 30},
    {"id": 1831, "subject_id": 18, "name": "३१. आकृती मालिका (Missing Image)", "description": "", "order": 31},
    {"id": 1832, "subject_id": 18, "name": "३२. आरशातील प्रतिमा (Mirror Image)", "description": "", "order": 32},
    {"id": 1833, "subject_id": 18, "name": "३३. पाण्यातील प्रतिमा (Water Image)", "description": "", "order": 33},
    {"id": 1834, "subject_id": 18, "name": "३४. आकृत्यांची मोजणी (Counting Figures)", "description": "", "order": 34},
    {"id": 1835, "subject_id": 18, "name": "३५. कागदाची घडी (Paper Folding)", "description": "", "order": 35},
    {"id": 1836, "subject_id": 18, "name": "३६. विसंगत आकृत्या (Odd Figures)", "description": "", "order": 36},
    {"id": 1837, "subject_id": 18, "name": "३७. संकीर्ण (Others)", "description": "", "order": 37},
    {"id": 1901, "subject_id": 19, "name": "०१. तार्किक क्षमता (Logical Reasoning)", "description": "", "order": 1},
    {"id": 1902, "subject_id": 19, "name": "०२. निर्णय क्षमता (Decision Making)", "description": "", "order": 2},
    {"id": 2001, "subject_id": 20, "name": "१. मराठी भाषेचा उगम, इतिहास व व्याकरण", "description": "", "order": 1},
    {"id": 2002, "subject_id": 20, "name": "२. लिपी व तिचे प्रकार", "description": "", "order": 2},
    {"id": 2003, "subject_id": 20, "name": "३. वर्णमाला व वर्णांचे प्रकार", "description": "", "order": 3},
    {"id": 2004, "subject_id": 20, "name": "४. वर्णांची उच्चारस्थाने", "description": "", "order": 4},
    {"id": 2005, "subject_id": 20, "name": "५. परसवर्ण", "description": "", "order": 5},
    {"id": 2006, "subject_id": 20, "name": "६. जोडाक्षरे व आघात", "description": "", "order": 6},
    {"id": 2007, "subject_id": 20, "name": "७. स्वर संधी", "description": "", "order": 7},
    {"id": 2008, "subject_id": 20, "name": "८. व्यंजन संधी", "description": "", "order": 8},
    {"id": 2009, "subject_id": 20, "name": "९. विसर्ग संधी", "description": "", "order": 9},
    {"id": 2010, "subject_id": 20, "name": "१०. पररूप / पूर्वरूप / मराठी विशेष संधी", "description": "", "order": 10},
    {"id": 2011, "subject_id": 20, "name": "११. शब्दांच्या जाती (मूलभूत संकल्पना)", "description": "", "order": 11},
    {"id": 2012, "subject_id": 20, "name": "१२. नाम व नामाचे प्रकार", "description": "", "order": 12},
    {"id": 2013, "subject_id": 20, "name": "१३. लिंग विचार", "description": "", "order": 13},
    {"id": 2014, "subject_id": 20, "name": "१४. वचन विचार", "description": "", "order": 14},
    {"id": 2015, "subject_id": 20, "name": "१५. विभक्ती व विभक्तीचे अर्थ (कारकार्थ व उपपदार्थ)", "description": "", "order": 15},
    {"id": 2016, "subject_id": 20, "name": "१६. सामान्यरूप", "description": "", "order": 16},
    {"id": 2017, "subject_id": 20, "name": "१७. सर्वनाम व सर्वनामाचे प्रकार", "description": "", "order": 17},
    {"id": 2018, "subject_id": 20, "name": "१८. विशेषण व विशेषणाचे प्रकार", "description": "", "order": 18},
    {"id": 2019, "subject_id": 20, "name": "१९. धातू, धातूसाधिते, कर्ता व कर्म", "description": "", "order": 19},
    {"id": 2020, "subject_id": 20, "name": "२०. क्रियापद व क्रियापदाचे प्रकार", "description": "", "order": 20},
    {"id": 2021, "subject_id": 20, "name": "२१. आख्यात व आख्याताचे अर्थ", "description": "", "order": 21},
    {"id": 2022, "subject_id": 20, "name": "२२. काळ व काळाचे प्रकार / अर्थ", "description": "", "order": 22},
    {"id": 2023, "subject_id": 20, "name": "२३. क्रियाविशेषण अव्यय", "description": "", "order": 23},
    {"id": 2024, "subject_id": 20, "name": "२४. शब्दयोगी अव्यय", "description": "", "order": 24},
    {"id": 2025, "subject_id": 20, "name": "२५. उभयान्वयी अव्यय", "description": "", "order": 25},
    {"id": 2026, "subject_id": 20, "name": "२६. केवलप्रयोगी अव्यय", "description": "", "order": 26},
    {"id": 2027, "subject_id": 20, "name": "२७. प्रयोग व प्रयोगाचे प्रकार", "description": "", "order": 27},
    {"id": 2028, "subject_id": 20, "name": "२८. समास व समासाचे प्रकार", "description": "", "order": 28},
    {"id": 2029, "subject_id": 20, "name": "२९. सिद्ध व साधित शब्द", "description": "", "order": 29},
    {"id": 2030, "subject_id": 20, "name": "३०. तत्सम, तद्भव व देशी शब्द", "description": "", "order": 30},
    {"id": 2031, "subject_id": 20, "name": "३१. परभाषिक शब्द", "description": "", "order": 31},
    {"id": 2032, "subject_id": 20, "name": "३२. उपसर्गघटित व प्रत्ययघटित शब्द", "description": "", "order": 32},
    {"id": 2033, "subject_id": 20, "name": "३३. वाक्य पृथक्करण", "description": "", "order": 33},
    {"id": 2034, "subject_id": 20, "name": "३४. वाक्य प्रकार व वाक्यरचना", "description": "", "order": 34},
    {"id": 2035, "subject_id": 20, "name": "३५. वाक्यपरिवर्तन / वाक्य रूपांतर", "description": "", "order": 35},
    {"id": 2036, "subject_id": 20, "name": "३६. वाक्य संश्लेषण", "description": "", "order": 36},
    {"id": 2037, "subject_id": 20, "name": "३७. वृत्ते", "description": "", "order": 37},
    {"id": 2038, "subject_id": 20, "name": "३८. अलंकार", "description": "", "order": 38},
    {"id": 2039, "subject_id": 20, "name": "३९. शब्दशक्ती, काव्य रस व ध्वन्यार्थ", "description": "", "order": 39},
    {"id": 2040, "subject_id": 20, "name": "४०. विरामचिन्हे", "description": "", "order": 40},
    {"id": 2041, "subject_id": 20, "name": "४१. शुद्धलेखनाचे नियम व शुद्ध-अशुद्ध शब्द", "description": "", "order": 41},
    {"id": 2042, "subject_id": 20, "name": "४२. समानार्थी व विरुद्धार्थी शब्द", "description": "", "order": 42},
    {"id": 2043, "subject_id": 20, "name": "४३. वाक्प्रचार व म्हणी", "description": "", "order": 43},
    {"id": 2044, "subject_id": 20, "name": "४४. अलंकारिक शब्द व एकाच शब्दाचे अनेक अर्थ", "description": "", "order": 44},
    {"id": 2045, "subject_id": 20, "name": "४५. शब्दसमूहाबद्दल एक शब्द व योग्य शब्द/विधान", "description": "", "order": 45},
    {"id": 2046, "subject_id": 20, "name": "४६. पारिभाषिक शब्द व जोडशब्द", "description": "", "order": 46},
    {"id": 2047, "subject_id": 20, "name": "४७. उताऱ्यावरील प्रश्न (आकलन)", "description": "", "order": 47},
    {"id": 2101, "subject_id": 21, "name": "1. Parts of Speech & Word Formation", "description": "", "order": 1},
    {"id": 2102, "subject_id": 21, "name": "2. Noun (Types & Rules)", "description": "", "order": 2},
    {"id": 2103, "subject_id": 21, "name": "3. Gender Rules", "description": "", "order": 3},
    {"id": 2104, "subject_id": 21, "name": "4. Number (Singular & Plural)", "description": "", "order": 4},
    {"id": 2105, "subject_id": 21, "name": "5. Pronoun (Types & Usage)", "description": "", "order": 5},
    {"id": 2106, "subject_id": 21, "name": "6. Adjective (Types & Order)", "description": "", "order": 6},
    {"id": 2107, "subject_id": 21, "name": "7. Verb & Auxiliary Verbs", "description": "", "order": 7},
    {"id": 2108, "subject_id": 21, "name": "8. Modal Auxiliaries / Modals", "description": "", "order": 8},
    {"id": 2109, "subject_id": 21, "name": "9. Mood of Verb", "description": "", "order": 9},
    {"id": 2110, "subject_id": 21, "name": "10. Adverb (Types & Positions)", "description": "", "order": 10},
    {"id": 2111, "subject_id": 21, "name": "11. Preposition & Suitable Words", "description": "", "order": 11},
    {"id": 2112, "subject_id": 21, "name": "12. Conjunctions & Connectors", "description": "", "order": 12},
    {"id": 2113, "subject_id": 21, "name": "13. Interjection", "description": "", "order": 13},
    {"id": 2114, "subject_id": 21, "name": "14. Articles (A, An, The)", "description": "", "order": 14},
    {"id": 2115, "subject_id": 21, "name": "15. Punctuation Marks", "description": "", "order": 15},
    {"id": 2116, "subject_id": 21, "name": "16. Tenses & Time Aspects", "description": "", "order": 16},
    {"id": 2117, "subject_id": 21, "name": "17. Voice (Active & Passive Voice)", "description": "", "order": 17},
    {"id": 2118, "subject_id": 21, "name": "18. Degrees of Comparison", "description": "", "order": 18},
    {"id": 2119, "subject_id": 21, "name": "19. Direct & Indirect Speech", "description": "", "order": 19},
    {"id": 2120, "subject_id": 21, "name": "20. Types of Sentences (Affirmative, Negative, Exclamatory, Interrogative)", "description": "", "order": 20},
    {"id": 2121, "subject_id": 21, "name": "21. Sentence Transformation (Simple, Compound, Complex)", "description": "", "order": 21},
    {"id": 2122, "subject_id": 21, "name": "22. Specific Transformations (As soon as, Too, Not only but also)", "description": "", "order": 22},
    {"id": 2123, "subject_id": 21, "name": "23. Question Tag", "description": "", "order": 23},
    {"id": 2124, "subject_id": 21, "name": "24. Clauses (Noun, Adjective, Adverb Clauses)", "description": "", "order": 24},
    {"id": 2125, "subject_id": 21, "name": "25. Formation & Structure of Questions", "description": "", "order": 25},
    {"id": 2126, "subject_id": 21, "name": "26. Figures of Speech", "description": "", "order": 26},
    {"id": 2127, "subject_id": 21, "name": "27. Synonyms & Similar Words", "description": "", "order": 27},
    {"id": 2128, "subject_id": 21, "name": "28. Antonyms & Opposite Words", "description": "", "order": 28},
    {"id": 2129, "subject_id": 21, "name": "29. Homonyms, Homophones & Polysemy", "description": "", "order": 29},
    {"id": 2130, "subject_id": 21, "name": "30. One Word Substitution", "description": "", "order": 30},
    {"id": 2131, "subject_id": 21, "name": "31. Confusing Words / Words Often Confused", "description": "", "order": 31},
    {"id": 2132, "subject_id": 21, "name": "32. Correct Spelling", "description": "", "order": 32},
    {"id": 2133, "subject_id": 21, "name": "33. Idioms & Phrases", "description": "", "order": 33},
    {"id": 2134, "subject_id": 21, "name": "34. Common Errors & Spotting the Error", "description": "", "order": 34},
    {"id": 2135, "subject_id": 21, "name": "35. Correct Sentence Selection", "description": "", "order": 35},
    {"id": 2136, "subject_id": 21, "name": "36. Correct Order of Sentences / Parajumbles", "description": "", "order": 36},
    {"id": 2137, "subject_id": 21, "name": "37. Suffix and Prefix", "description": "", "order": 37},
    {"id": 2138, "subject_id": 21, "name": "38. Suitable Word / Meaning of Word", "description": "", "order": 38},
    {"id": 2139, "subject_id": 21, "name": "39. Reading Comprehension Passage", "description": "", "order": 39},
    {"id": 2201, "subject_id": 22, "name": "महाराष्ट्र, राष्ट्रीय व जागतिक चालू घडामोडी", "description": "", "order": 1}
]


def init_session():
    if "subjects" not in st.session_state:
        if os.path.exists("subjects_topics.json"):
            try:
                with open("subjects_topics.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    st.session_state.subjects = data.get("subjects", MARATHI_SUBJECTS)
                    st.session_state.topics = data.get("topics", MARATHI_TOPICS)
            except Exception:
                st.session_state.subjects = MARATHI_SUBJECTS
                st.session_state.topics = MARATHI_TOPICS
        else:
            st.session_state.subjects = MARATHI_SUBJECTS
            st.session_state.topics = MARATHI_TOPICS

    if "parsed_questions" not in st.session_state:
        st.session_state.parsed_questions = []

    if "paper_info" not in st.session_state:
        st.session_state.paper_info = {
            "exam_type": "MPSC_RAJYASEVA",
            "paper_stage": "PRELIMS",
            "year": 2026,
            "paper_number": 1,
            "paper_label": "सामान्य अध्ययन पेपर १",
            "language": "EN_MR"
        }


init_session()


# --------------------------------------------------------
# 2. Gemini PDF Extraction Prompts & Functions
# --------------------------------------------------------

def build_dual_pdf_prompt(subjects, topics, has_key_pdf=False, start_question=None):
    """Builds an integrated Gemini prompt for processing Question Paper PDF and optional Answer Key PDF concurrently.

    If start_question is provided, the model is instructed to skip all
    questions before that number (they were already extracted in a previous
    run) and continue extracting from that question number to the end of the
    paper — used for resumable/continuation extraction.
    """
    subject_lookup = [{"id": s["id"], "name": s["name"]} for s in subjects]
    topic_lookup = [{"id": t["id"], "subject_id": t["subject_id"], "name": t["name"]} for t in topics]

    key_instruction = """
7. ANSWER KEY MATCHING:
   - You have been provided with BOTH the Question Paper PDF and the Answer Key PDF.
   - Read the correct answer option (1, 2, 3, or 4 / A, B, C, or D) for each question from the Answer Key PDF.
   - Map it directly to "correct_option" ('A', 'B', 'C', or 'D').
""" if has_key_pdf else """
7. Set "correct_option" to empty string "" if not determinable.
"""

    if start_question:
        continuation_instruction = f"""
CONTINUATION MODE (IMPORTANT):
- Questions numbered 1 to {start_question - 1} have ALREADY been extracted in a
  previous run and must NOT be included in your output again.
- Start your extraction at question number {start_question} and continue
  extracting every question from there to the LAST question in the paper.
  Do not stop early, do not skip any question, and do not repeat questions
  before {start_question}.
"""
    else:
        continuation_instruction = ""

    prompt = f"""
You are an expert MPSC exam paper parser and subject-matter expert.

Task:
1. Examine the provided MPSC Question Paper PDF.
2. IMPORTANT: Skip Page 1 (Cover / Details) and Skip the Last Page (Sample / Instructions).
3. Process all middle question pages.
4. Extract every single question in exact numerical order (Q1, Q2, Q3...), covering the ENTIRE paper with no omissions.
{continuation_instruction}
5. LANGUAGE-FAITHFUL EXTRACTION FORMAT (CRITICAL — DO NOT AUTO-TRANSLATE):
   - Look at each question exactly as printed in the source PDF and determine
     which language(s) are ACTUALLY PRESENT for that question, field by field
     (`question_text`, `option_a`, `option_b`, `option_c`, `option_d`):
     a) If BOTH English and Marathi are printed for that field in the source
        PDF (as is common in MPSC bilingual papers), output it as:
        "English Text [[MR]] मराठी मजकूर" — English first, then the literal
        separator ` [[MR]] `, then the Marathi text, using the wording
        exactly as printed in the source (do not paraphrase or re-translate
        text that is already given in both languages).
     b) If ONLY English is printed for that field in the source PDF, output
        the field containing ONLY that English text, exactly as printed —
        and set the corresponding "*_mr" null-flag field (see field list
        below) to true, meaning "no Marathi text exists in the source for
        this field." Do NOT fabricate a Marathi translation.
     c) If ONLY Marathi is printed for that field in the source PDF, output
        the field containing ONLY that Marathi text, exactly as printed —
        and set the corresponding "*_en" null-flag field to true, meaning
        "no English text exists in the source for this field." Do NOT
        fabricate an English translation.
   - For EVERY question object, in addition to question_text/option_a-d,
     ALSO include these boolean null-flag fields (default false when both
     languages are present, or when not applicable):
     "question_text_mr_missing", "question_text_en_missing",
     "option_a_mr_missing", "option_a_en_missing",
     "option_b_mr_missing", "option_b_en_missing",
     "option_c_mr_missing", "option_c_en_missing",
     "option_d_mr_missing", "option_d_en_missing"
   - These null-flags let the downstream tool store `null` for whichever
     language genuinely does not exist in the source, instead of guessing.
6. Extract options (1), (2), (3), (4) into option_a, option_b, option_c, option_d respectively.
{key_instruction}
8. If a question contains a diagram, map, or image figure, extract its reference identifier into "question_image" (otherwise set null).
9. AUTOMATIC CLASSIFICATION TASK: Analyze each question text carefully and select the most accurate subject_id and topic_id from the reference syllabus index list provided below.
10. EXPLANATION GENERATION TASK (always bilingual regardless of source language, since these are newly generated, not source text):
   - Provide a concise summary explanation in "explanation" formatted as: "English Concise Explanation. [[MR]] मराठी संक्षिप्त स्पष्टीकरण."
   - Provide a detailed conceptual explanation in "explanation_detail" formatted as: "English Detailed Explanation. [[MR]] मराठी सविस्तर स्पष्टीकरण."

Reference Subjects List:
{json.dumps(subject_lookup, ensure_ascii=False)}

Reference Topics List:
{json.dumps(topic_lookup, ensure_ascii=False)}

Output MUST be a strictly valid JSON array of objects. Return ONLY raw JSON array without markdown backticks.

Example Output Structure (bilingual question, both languages present in source):
[
  {{
    "question_number": 1,
    "question_text": "The Quit India Movement was launched in which year? [[MR]] 'भारत छोडो चळवळ' कोणत्या वर्षी सुरू झाली होती?",
    "question_text_mr_missing": false,
    "question_text_en_missing": false,
    "question_image": null,
    "option_a": "1940 [[MR]] १९४०",
    "option_a_mr_missing": false,
    "option_a_en_missing": false,
    "option_b": "1941 [[MR]] १९४१",
    "option_b_mr_missing": false,
    "option_b_en_missing": false,
    "option_c": "1942 [[MR]] १९४२",
    "option_c_mr_missing": false,
    "option_c_en_missing": false,
    "option_d": "1943 [[MR]] १९४३",
    "option_d_mr_missing": false,
    "option_d_en_missing": false,
    "correct_option": "C",
    "subject_id": 5,
    "topic_id": 522,
    "explanation": "The Quit India Movement was launched by Mahatma Gandhi on 8 August 1942 at the Bombay session of AICC with the slogan Do or Die. [[MR]] महात्मा गांधींनी ८ ऑगस्ट १९४२ रोजी ऑल इंडिया काँग्रेस कमिटीच्या मुंबई अधिवेशनात 'करा किंवा मरा' चा नारा देऊन 'भारत छोडो चळवळ' सुरू केली होती.",
    "explanation_detail": "Gandhi gave the historic slogan \"Do or Die\" (Karo ya Maro). The British immediately arrested Gandhi, Nehru and other Congress leaders. Major centres of revolt included Satara in Maharashtra, Midnapur in Bengal, and Ballia in UP. The movement was largely suppressed by 1944. [[MR]] गांधीजींनी \"करा किंवा मरा\" ही ऐतिहासिक घोषणा दिली. ब्रिटिशांनी लागलीच गांधीजी, नेहरू आणि काँग्रेसच्या इतर प्रमुख नेत्यांना अटक केली. या उठावाच्या प्रमुख केंद्रांमध्ये महाराष्ट्रातील सातारा, बंगालमधील मिदनापूर आणि उत्तर प्रदेशातील बलिया यांचा समावेश होता. १९४४ पर्यंत ही चळवळ मोठ्या प्रमाणावर दडपली गेली.",
    "explanation_image1": null
  }},
  {{
    "question_number": 2,
    "question_text": "Which article of the Indian Constitution deals with the Right to Equality?",
    "question_text_mr_missing": true,
    "question_text_en_missing": false,
    "question_image": null,
    "option_a": "Article 12",
    "option_a_mr_missing": true,
    "option_a_en_missing": false,
    "option_b": "Article 14",
    "option_b_mr_missing": true,
    "option_b_en_missing": false,
    "option_c": "Article 19",
    "option_c_mr_missing": true,
    "option_c_en_missing": false,
    "option_d": "Article 21",
    "option_d_mr_missing": true,
    "option_d_en_missing": false,
    "correct_option": "B",
    "subject_id": 1,
    "topic_id": 105,
    "explanation": "Article 14 of the Indian Constitution guarantees the Right to Equality before law. [[MR]] भारतीय राज्यघटनेच्या अनुच्छेद १४ मध्ये कायद्यासमोर समानतेचा हक्क हमी दिला आहे.",
    "explanation_detail": "Article 14 ensures equality before law and equal protection of laws to all persons within the territory of India, forming part of the Fundamental Rights under Part III. [[MR]] अनुच्छेद १४ भारताच्या हद्दीतील सर्व व्यक्तींना कायद्यासमोर समानता आणि कायद्यांचे समान संरक्षण सुनिश्चित करते, जे भाग III अंतर्गत मूलभूत हक्कांचा भाग आहे.",
    "explanation_image1": null
  }}
]

Note: in the second example, the source PDF had this question in English
only, so all "*_mr_missing" flags for that question are true (Marathi is
absent in the source), and the tool downstream will store null for the
Marathi side of those fields — while "explanation"/"explanation_detail"
remain bilingual per rule 10, since those are AI-generated, not source text.
"""
    return prompt


def _apply_null_language_flags(item):
    """Given a raw Gemini-extracted question dict (with bilingual '[[MR]]'
    text and boolean *_missing flags), returns a new dict where question_text
    and option_a-d are split into explicit language-null-aware values:
    - If both languages present: keep the combined "English [[MR]] Marathi" string.
    - If only English present: keep only English text, no [[MR]] marker.
    - If only Marathi present: keep only Marathi text, no [[MR]] marker.
    A missing language is represented as null in the accompanying
    "<field>_language" metadata so downstream consumers know which
    language(s) are actually populated.
    """
    def process_field(field_name):
        raw_value = item.get(field_name, "") or ""
        mr_missing = bool(item.get(f"{field_name}_mr_missing", False))
        en_missing = bool(item.get(f"{field_name}_en_missing", False))

        if mr_missing and not en_missing:
            # Only English present in source; strip any accidental [[MR]] content.
            eng_part = raw_value.split("[[MR]]")[0].strip()
            return eng_part, "EN", None
        elif en_missing and not mr_missing:
            # Only Marathi present in source; strip any accidental [[MR]] content.
            parts = raw_value.split("[[MR]]")
            mar_part = parts[-1].strip() if len(parts) > 1 else raw_value.strip()
            return mar_part, "MR", None
        else:
            # Both present (or flags absent/ambiguous) -> keep combined bilingual value.
            return raw_value, "EN_MR", raw_value

    result = {}
    for field_name in ["question_text", "option_a", "option_b", "option_c", "option_d"]:
        value, lang_flag, _ = process_field(field_name)
        result[field_name] = value
        result[f"{field_name}_language"] = lang_flag
    return result


def _extract_pdfs_with_gemini_core(paper_pdf, key_pdf, api_key, start_question=None):
    """Shared core: uploads PDFs, builds the prompt (optionally with a
    continuation start_question), calls Gemini across candidate models, and
    returns the parsed raw JSON array (before null-language post-processing)."""
    client = genai.Client(api_key=api_key)

    tmp_paths = []
    gemini_files = []

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_p:
            tmp_p.write(paper_pdf.getvalue())
            tmp_paths.append(tmp_p.name)

        st.info("Question Paper PDF अपलोड होत आहे...")
        gemini_paper_file = client.files.upload(file=tmp_paths[0])
        gemini_files.append(gemini_paper_file)

        contents_payload = [gemini_paper_file]

        has_key = False
        if key_pdf is not None:
            has_key = True
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_k:
                tmp_k.write(key_pdf.getvalue())
                tmp_paths.append(tmp_k.name)

            st.info("Answer Key PDF अपलोड होत आहे...")
            gemini_key_file = client.files.upload(file=tmp_paths[1])
            gemini_files.append(gemini_key_file)
            contents_payload.append(gemini_key_file)

        if start_question:
            st.info(f"Gemini AI द्वारे प्रश्न क्रमांक {start_question} पासून पुढे संकलन (Continuation) चालू आहे...")
        else:
            st.info("Gemini AI द्वारे दोन्ही फाईल्सचे एकाच वेळी विश्लेषण करून प्रश्न, उत्तरे, स्पष्टीकरणे व विषय वर्गीकरण तयार केले जात आहे...")

        prompt_text = build_dual_pdf_prompt(
            st.session_state.subjects,
            st.session_state.topics,
            has_key_pdf=has_key,
            start_question=start_question
        )
        contents_payload.append(prompt_text)

        # Same Gemini model list as the original working code.
        candidate_models = [
            "gemini-2.5-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-1.5-flash",
            "gemini-2.0-flash",
        ]

        response = None
        last_error = None

        for model_name in candidate_models:
            try:
                st.info(f"मॉडेल `{model_name}` द्वारे प्रक्रिया चालू आहे...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents_payload
                )
                if response and response.text:
                    st.success(f"मॉडेल `{model_name}` द्वारे PDF यशस्वीरीत्या विश्लेषित झाली!")
                    break
            except Exception as err:
                last_error = err
                continue

        for g_file in gemini_files:
            try:
                client.files.delete(name=g_file.name)
            except Exception:
                pass

        for path in tmp_paths:
            if os.path.exists(path):
                os.remove(path)

        if not response or not response.text:
            raise Exception(f"सर्व मॉडेल निष्फळ ठरले. शेवटची त्रुटी: {last_error}")

        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

        parsed_json = json.loads(raw_text.strip())
        return parsed_json

    except Exception as e:
        for path in tmp_paths:
            if os.path.exists(path):
                os.remove(path)
        st.error(f"Gemini API प्रक्रिया त्रुटी: {e}")
        return []


def process_both_pdfs_with_gemini(paper_pdf, key_pdf, api_key):
    """Full (fresh) extraction run — from question 1 to the end of the paper."""
    return _extract_pdfs_with_gemini_core(paper_pdf, key_pdf, api_key, start_question=None)


def process_pdf_continuation(paper_pdf, key_pdf, api_key, start_question):
    """Continuation extraction run — resumes from a specific question number
    using the same paper PDF, for when a previous run only returned a
    partial set of questions (e.g. due to model output limits)."""
    return _extract_pdfs_with_gemini_core(paper_pdf, key_pdf, api_key, start_question=start_question)


# --------------------------------------------------------
# 3. Separate Answer Key Parsing Functions
# --------------------------------------------------------

ANSWER_KEY_PROMPT = """
You are an expert exam answer key extractor.
Examine this answer key document or image/PDF.
Extract all Question Numbers and their corresponding Correct Option (A, B, C, or D / 1, 2, 3, or 4).

Output MUST be a valid JSON object mapping Question Numbers (as strings/integers) to their Correct Option letter ('A', 'B', 'C', or 'D').
Example format:
{
  "1": "A",
  "2": "C",
  "3": "B",
  "4": "D"
}
Return ONLY raw JSON without markdown backticks.
"""

def extract_answer_key_from_pdf(pdf_file, api_key):
    """Uses Gemini API to extract Answer Key mapping directly from a standalone PDF file."""
    client = genai.Client(api_key=api_key)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(pdf_file.getvalue())
        tmp_path = tmp_file.name

    try:
        gemini_file = client.files.upload(file=tmp_path)

        candidate_models = [
            "gemini-2.5-flash",
            "gemini-3.5-flash",
            "gemini-1.5-flash",
            "gemini-2.0-flash",
        ]

        response = None
        for model_name in candidate_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[gemini_file, ANSWER_KEY_PROMPT]
                )
                if response and response.text:
                    break
            except Exception:
                continue

        try:
            client.files.delete(name=gemini_file.name)
        except Exception:
            pass

        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        if not response or not response.text:
            return {}

        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

        return json.loads(raw_text.strip())

    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        st.error(f"Answer Key PDF Parsing Error: {e}")
        return {}


def apply_answer_key_dict(ans_map):
    """Applies a dictionary answer map {"1": "A", "2": "B"} to parsed questions."""
    if not st.session_state.parsed_questions:
        st.error("उत्तरतालिका लागू करण्यासाठी कोणतेही प्रश्न उपलब्ध नाहीत.")
        return 0

    updated_count = 0
    for q in st.session_state.parsed_questions:
        q_no_str = str(q.get("question_number"))
        if q_no_str in ans_map:
            opt_upper = str(ans_map[q_no_str]).upper().strip()
            if opt_upper in ['1', '2', '3', '4']:
                num_to_alpha = {'1': 'A', '2': 'B', '3': 'C', '4': 'D'}
                opt_upper = num_to_alpha[opt_upper]
            q["correct_option"] = opt_upper
            updated_count += 1

    return updated_count


def apply_answer_key_text(answer_text):
    """Parses answer key text formats and updates correct_option."""
    if not st.session_state.parsed_questions:
        st.error("उत्तरतालिका लागू करण्यासाठी कोणतेही प्रश्न उपलब्ध नाहीत.")
        return 0

    matches = re.findall(r'(\d{1,3})\s*[:\-\=\.\s]+\s*([a-dA-D1-4])', answer_text)

    if not matches:
        st.warning("उत्तरतालिकेचे स्वरूप ओळखता आले नाही. उदाहरण: `1-A, 2-B, 3-C` किंवा `1:1, 2:3`.")
        return 0

    ans_map = {}
    for q_num_str, opt_str in matches:
        ans_map[q_num_str] = opt_str

    return apply_answer_key_dict(ans_map)


def build_one_line_per_record_json(final_json):
    """Serializes final_json so that:
    - the top-level structure (generated_at, exam_type, ..., subjects, topics,
      questions) stays multi-line and readable, and
    - EVERY individual subject object, topic object, and question object is
      rendered on its own single line (no field-by-field line breaks inside
      an object), so scanning/searching the file by subject/topic/question is
      easy (one subject per line, one topic per line, one question per line).

    Embedded newlines inside string values (e.g. explanation_detail's "\\n")
    remain valid JSON escape sequences and do not break the one-line-per-record
    layout, since json.dumps already escapes them as "\\n" rather than literal
    newlines.
    """
    def compact_item(item):
        # separators=(',', ': ') keeps a readable "key": value spacing while
        # still emitting the whole object on a single line.
        return json.dumps(item, ensure_ascii=False, separators=(',', ': '))

    def render_array(key, items, indent="  "):
        if not items:
            return f'{indent}"{key}": []'
        lines = [f'{indent}"{key}": [']
        inner_indent = indent + "  "
        for idx, item in enumerate(items):
            comma = "," if idx < len(items) - 1 else ""
            lines.append(f"{inner_indent}{compact_item(item)}{comma}")
        lines.append(f"{indent}]")
        return "\n".join(lines)

    top_level_keys = [
        "generated_at", "exam_type", "paper_stage", "year",
        "paper_number", "paper_label"
    ]

    parts = ["{"]
    for key in top_level_keys:
        if key in final_json:
            value_json = json.dumps(final_json[key], ensure_ascii=False)
            parts.append(f'  "{key}": {value_json},')

    parts.append(render_array("subjects", final_json.get("subjects", [])) + ",")
    parts.append(render_array("topics", final_json.get("topics", [])) + ",")
    parts.append(render_array("questions", final_json.get("questions", [])))
    parts.append("}")

    return "\n".join(parts)


def build_formatted_question(item, language):
    """Turns a raw Gemini-extracted item into the internal question dict used
    by the editor UI, applying the null-language splitting logic."""
    lang_split = _apply_null_language_flags(item)

    return {
        "question_number": item.get("question_number", 0),
        "question_text": lang_split["question_text"],
        "question_text_language": lang_split["question_text_language"],
        "question_image": item.get("question_image", None),
        "option_a": lang_split["option_a"],
        "option_a_language": lang_split["option_a_language"],
        "option_b": lang_split["option_b"],
        "option_b_language": lang_split["option_b_language"],
        "option_c": lang_split["option_c"],
        "option_c_language": lang_split["option_c_language"],
        "option_d": lang_split["option_d"],
        "option_d_language": lang_split["option_d_language"],
        "correct_option": item.get("correct_option", ""),
        "difficulty": item.get("difficulty", "MEDIUM"),
        "subject_id": item.get("subject_id", None),
        "topic_id": item.get("topic_id", None),
        "new_subject_name": "",
        "new_topic_name": "",
        "reference": item.get("reference", ""),
        "explanation": item.get("explanation", ""),
        "explanation_detail": item.get("explanation_detail", ""),
        "explanation_image1": item.get("explanation_image1", None),
        "language": language
    }


# --------------------------------------------------------
# 4. Sidebar: Custom Subject/Topic Manager
# --------------------------------------------------------

with st.sidebar:
    st.header("⚙️ विषय व उपघटक व्यवस्थापन")

    with st.expander("➕ नवीन विषय जोडा"):
        new_s_name = st.text_input("विषयाचे नाव")
        new_s_desc = st.text_input("विवरण", value="")
        if st.button("विषय जतन करा"):
            if new_s_name.strip():
                new_s_id = max([s["id"] for s in st.session_state.subjects], default=0) + 1
                st.session_state.subjects.append({
                    "id": new_s_id,
                    "name": new_s_name.strip(),
                    "description": new_s_desc.strip(),
                    "color_hex": "#607D8B",
                    "icon": "book",
                    "order": len(st.session_state.subjects) + 1
                })
                st.success(f"नवीन विषय जोडला: {new_s_name}")
                st.rerun()

    with st.expander("➕ नवीन उपघटक (Topic) जोडा"):
        sub_parent_id = st.selectbox(
            "मुख्य विषय",
            options=[s["id"] for s in st.session_state.subjects],
            format_func=lambda sid: next((s["name"] for s in st.session_state.subjects if s["id"] == sid), "")
        )
        new_t_name = st.text_input("उपघटकाचे नाव")
        if st.button("उपघटक जतन करा"):
            if new_t_name.strip():
                new_t_id = max([t["id"] for t in st.session_state.topics], default=0) + 1
                st.session_state.topics.append({
                    "id": new_t_id,
                    "subject_id": sub_parent_id,
                    "name": new_t_name.strip(),
                    "description": "",
                    "order": 0
                })
                st.success(f"नवीन उपघटक जोडला: {new_t_name}")
                st.rerun()

    if st.button("🔄 मूळ इंडेक्सवर रीसेट करा", type="secondary"):
        st.session_state.subjects = MARATHI_SUBJECTS
        st.session_state.topics = MARATHI_TOPICS
        st.success("इंडेक्सवर रीसेट केले.")
        st.rerun()


# --------------------------------------------------------
# 5. UI Step 1: Paper Information & Config
# --------------------------------------------------------

st.divider()
st.header("पायरी १ : API की व परीक्षेची माहिती")

c_api, c_meta = st.columns([1, 2])

with c_api:
    gemini_api_key = st.text_input(
        "Gemini API Key टाका (PDF प्रक्रियेसाठी आवश्यक)",
        value=os.getenv("GEMINI_API_KEY", ""),
        type="password",
        help="https://aistudio.google.com/ वरून मोफत की मिळवा"
    )

with c_meta:
    col1, col2, col3 = st.columns(3)

    exam_types = ["MPSC_GROUP_B_COMBINE", "MPSC_GROUP_C_COMBINE", "MPSC_RAJYASEVA", "OTHER"]
    paper_stages = ["PRELIMS", "MAINS"]
    languages = ["EN_MR", "MR", "EN"]

    cur_exam = st.session_state.paper_info.get("exam_type", "MPSC_RAJYASEVA")
    cur_stage = st.session_state.paper_info.get("paper_stage", "PRELIMS")
    cur_lang = st.session_state.paper_info.get("language", "EN_MR")

    with col1:
        exam_type = st.selectbox("परीक्षेचा प्रकार", exam_types, index=exam_types.index(cur_exam) if cur_exam in exam_types else 0)
        paper_stage = st.selectbox("परीक्षेचा टप्पा", paper_stages, index=paper_stages.index(cur_stage) if cur_stage in paper_stages else 0)
    with col2:
        year = st.number_input("वर्ष", min_value=2000, max_value=2100, value=int(st.session_state.paper_info.get("year", 2026)))
        paper_number = st.number_input("पेपर क्रमांक", min_value=1, max_value=10, value=int(st.session_state.paper_info.get("paper_number", 1)))
    with col3:
        paper_label = st.text_input("पेपरचे नाव / लेबल", value=st.session_state.paper_info.get("paper_label", "सामान्य अध्ययन पेपर १"))
        language = st.selectbox("भाषा मोड", languages, index=languages.index(cur_lang) if cur_lang in languages else 0)

st.session_state.paper_info = {
    "exam_type": exam_type,
    "paper_stage": paper_stage,
    "year": int(year),
    "paper_number": int(paper_number),
    "paper_label": paper_label,
    "language": language
}


# --------------------------------------------------------
# 6. UI Step 2: Load Source Data & Answer Key
# --------------------------------------------------------

st.divider()
st.header("पायरी २ : प्रश्नपत्रिका PDF व उत्तरतालिका PDF अपलोड करा")

tab_pdf, tab_json, tab_key = st.tabs([
    "🚀 प्रश्नपत्रिका PDF + उत्तरतालिका PDF (Dual Upload)",
    "📂 जुनी JSON फाईल लोड करून एडिट करा",
    "🔑 स्वतंत्र उत्तरतालिका जोडा (PDF / TXT / Paste)"
])

# TAB 1: DUAL PDF UPLOADER (Question Paper + Answer Key concurrently)
with tab_pdf:
    col_pdf1, col_pdf2 = st.columns(2)

    with col_pdf1:
        uploaded_paper_pdf = st.file_uploader("१. MPSC प्रश्नपत्रिका PDF निवडा (Required)", type=["pdf"], key="paper_pdf_uploader")

    with col_pdf2:
        uploaded_key_pdf = st.file_uploader("२. अधिकृत उत्तरतालिका (Answer Key) PDF निवडा (Optional)", type=["pdf"], key="key_pdf_uploader")

    if uploaded_paper_pdf:
        st.success("प्रश्नपत्रिका PDF अपलोड झाली आहे.")
        if uploaded_key_pdf:
            st.success("उत्तरतालिका PDF देखील अपलोड झाली आहे.")

        # ---- Fresh full extraction ----
        if st.button("⚡ Gemini AI द्वारे नवीन (Fresh) प्रक्रिया सुरू करा", type="primary", use_container_width=True):
            if not gemini_api_key.strip():
                st.error("कृपया पायरी १ मध्ये वैध Gemini API Key टाका.")
            else:
                with st.spinner("प्रश्नपत्रिका व उत्तरतालिका दोन्ही PDF मधून प्रश्न, उत्तरे, स्पष्टीकरणे तयार करणे चालू आहे..."):
                    extracted_data = process_both_pdfs_with_gemini(uploaded_paper_pdf, uploaded_key_pdf, gemini_api_key.strip())

                    if extracted_data:
                        formatted_questions = [build_formatted_question(item, language) for item in extracted_data]
                        st.session_state.parsed_questions = formatted_questions
                        st.success(f"✅ एकूण {len(formatted_questions)} प्रश्न यशस्वीरीत्या उत्तरे, स्पष्टीकरणे व विषयांसह जनरेट झाले!")
                        st.rerun()

        st.markdown("---")

        # ---- Resumable continuation extraction ----
        st.subheader("🔁 टप्प्याटप्प्याने संकलन (Continuation) — मागील अपूर्ण JSON पासून पुढे सुरू ठेवा")
        st.caption("जर आधीच्या प्रक्रियेत फक्त काही प्रश्न (उदा. ३० पैकी ३०) JSON मध्ये आले असतील, तर ती JSON फाईल इथे अपलोड करा आणि पुढील प्रश्न क्रमांकापासून संकलन सुरू ठेवा. दोन्ही निकाल एकत्र (append) होतील.")

        col_cont1, col_cont2 = st.columns(2)
        with col_cont1:
            partial_json_upload = st.file_uploader(
                "मागील अपूर्ण JSON फाईल अपलोड करा (उदा. Q1-Q30 असलेली)",
                type=["json"],
                key="continuation_json_uploader"
            )

        detected_next_q = None
        if partial_json_upload is not None:
            try:
                partial_content = json.load(partial_json_upload)
                partial_json_upload.seek(0)
                partial_questions = partial_content.get("questions", [])
                if partial_questions:
                    max_q_no = max(int(q.get("question_number", 0)) for q in partial_questions)
                    detected_next_q = max_q_no + 1
                    st.info(f"अपलोड केलेल्या JSON मध्ये शेवटचा प्रश्न क्रमांक {max_q_no} आढळला. पुढील संकलन प्रश्न क्रमांक {detected_next_q} पासून सुरू होईल.")
            except Exception as err:
                st.error(f"अपलोड केलेली JSON वाचता आली नाही: {err}")

        with col_cont2:
            start_from_q = st.number_input(
                "पुढील प्रश्न क्रमांकापासून सुरू करा",
                min_value=1,
                max_value=1000,
                value=detected_next_q if detected_next_q else 1,
                step=1,
                key="continuation_start_q"
            )

        if st.button("▶️ प्रश्न क्रमांक " + str(int(start_from_q)) + " पासून पुढे संकलन सुरू ठेवा", use_container_width=True):
            if not gemini_api_key.strip():
                st.error("कृपया पायरी १ मध्ये वैध Gemini API Key टाका.")
            elif partial_json_upload is None:
                st.error("कृपया आधी मागील अपूर्ण JSON फाईल अपलोड करा, जेणेकरून आधीचे प्रश्न कायम राहतील.")
            else:
                try:
                    partial_json_upload.seek(0)
                    partial_content = json.load(partial_json_upload)
                except Exception as err:
                    st.error(f"अपलोड केलेली JSON वाचता आली नाही: {err}")
                    partial_content = None

                if partial_content is not None:
                    existing_raw_questions = partial_content.get("questions", [])
                    existing_formatted = []
                    for item in existing_raw_questions:
                        # Already-exported questions are in final format; load them directly
                        # (they already have null-language handling baked in from their own export).
                        existing_formatted.append({
                            "question_number": item.get("question_number", 0),
                            "question_text": item.get("question_text", ""),
                            "question_text_language": item.get("question_text_language", "EN_MR"),
                            "question_image": item.get("question_image", None),
                            "option_a": item.get("option_a", ""),
                            "option_a_language": item.get("option_a_language", "EN_MR"),
                            "option_b": item.get("option_b", ""),
                            "option_b_language": item.get("option_b_language", "EN_MR"),
                            "option_c": item.get("option_c", ""),
                            "option_c_language": item.get("option_c_language", "EN_MR"),
                            "option_d": item.get("option_d", ""),
                            "option_d_language": item.get("option_d_language", "EN_MR"),
                            "correct_option": item.get("correct_option", ""),
                            "difficulty": item.get("difficulty", "MEDIUM"),
                            "subject_id": item.get("subject_id", None),
                            "topic_id": item.get("topic_id", None),
                            "new_subject_name": "",
                            "new_topic_name": "",
                            "reference": item.get("reference", ""),
                            "explanation": item.get("explanation", ""),
                            "explanation_detail": item.get("explanation_detail", ""),
                            "explanation_image1": item.get("explanation_image1", None),
                            "language": item.get("language", language)
                        })

                    with st.spinner(f"प्रश्न क्रमांक {int(start_from_q)} पासून पुढे संकलन चालू आहे..."):
                        continuation_data = process_pdf_continuation(
                            uploaded_paper_pdf,
                            uploaded_key_pdf,
                            gemini_api_key.strip(),
                            start_question=int(start_from_q)
                        )

                        if continuation_data:
                            new_formatted = [build_formatted_question(item, language) for item in continuation_data]

                            # Merge: keep existing questions, append only new question_numbers not already present.
                            existing_numbers = {q["question_number"] for q in existing_formatted}
                            appended = [q for q in new_formatted if q["question_number"] not in existing_numbers]

                            merged = existing_formatted + appended
                            merged.sort(key=lambda q: q.get("question_number", 0))

                            st.session_state.parsed_questions = merged
                            st.success(f"✅ आधीचे {len(existing_formatted)} + नवीन {len(appended)} = एकूण {len(merged)} प्रश्न आता संकलित झाले!")
                            st.rerun()
                        else:
                            st.warning("पुढील प्रश्न मिळाले नाहीत. संपूर्ण पेपर आधीच संकलित झाला असेल किंवा AI कडून प्रतिसाद आला नाही.")

# TAB 2: JSON LOADER
with tab_json:
    uploaded_json = st.file_uploader("पूर्वी डाऊनलोड केलेली JSON फाईल निवडा", type=["json"], key="json_uploader")

    if uploaded_json:
        if st.button("📥 JSON फाईल एडिटरमध्ये लोड करा", type="secondary", use_container_width=True):
            try:
                content = json.load(uploaded_json)

                st.session_state.paper_info["exam_type"] = content.get("exam_type", exam_type)
                st.session_state.paper_info["paper_stage"] = content.get("paper_stage", paper_stage)
                st.session_state.paper_info["year"] = content.get("year", year)
                st.session_state.paper_info["paper_number"] = content.get("paper_number", paper_number)
                st.session_state.paper_info["paper_label"] = content.get("paper_label", paper_label)

                if "subjects" in content and isinstance(content["subjects"], list):
                    st.session_state.subjects = content["subjects"]
                if "topics" in content and isinstance(content["topics"], list):
                    st.session_state.topics = content["topics"]

                raw_questions = content.get("questions", [])
                loaded_questions = []

                for item in raw_questions:
                    loaded_questions.append({
                        "question_number": item.get("question_number", 0),
                        "question_text": item.get("question_text", ""),
                        "question_text_language": item.get("question_text_language", "EN_MR"),
                        "question_image": item.get("question_image", None),
                        "option_a": item.get("option_a", ""),
                        "option_a_language": item.get("option_a_language", "EN_MR"),
                        "option_b": item.get("option_b", ""),
                        "option_b_language": item.get("option_b_language", "EN_MR"),
                        "option_c": item.get("option_c", ""),
                        "option_c_language": item.get("option_c_language", "EN_MR"),
                        "option_d": item.get("option_d", ""),
                        "option_d_language": item.get("option_d_language", "EN_MR"),
                        "correct_option": item.get("correct_option", ""),
                        "difficulty": item.get("difficulty", "MEDIUM"),
                        "topic_id": item.get("topic_id", None),
                        "subject_id": item.get("subject_id", None),
                        "new_subject_name": "",
                        "new_topic_name": "",
                        "reference": item.get("reference", ""),
                        "explanation": item.get("explanation", ""),
                        "explanation_detail": item.get("explanation_detail", ""),
                        "explanation_image1": item.get("explanation_image1", None),
                        "language": item.get("language", language)
                    })

                st.session_state.parsed_questions = loaded_questions
                st.success(f"✅ JSON फाईलमधून {len(loaded_questions)} प्रश्न यशस्वीरीत्या लोड झाले!")
                st.rerun()

            except Exception as err:
                st.error(f"JSON फाईल वाचता आली नाही: {err}")

# TAB 3: STANDALONE ANSWER KEY UPLOADER
with tab_key:
    st.subheader("🔑 स्वतंत्र उत्तरतालिका (Answer Key) जोडणे")
    st.write("आधी लोड केलेल्या प्रश्नांना उत्तरतालिका जोडण्यासाठी PDF, TXT/CSV अपलोड करा किंवा मॅन्युअली पेस्ट करा.")

    col_k1, col_k2 = st.columns(2)

    with col_k1:
        key_file = st.file_uploader("उत्तरतालिका फाईल निवडा (.pdf, .txt किंवा .csv)", type=["pdf", "txt", "csv"], key="standalone_key_uploader")

    with col_k2:
        key_pasted_text = st.text_area(
            "किंवा उत्तरतालिका येथे मॅन्युअली पेस्ट करा",
            placeholder="उदाहरण:\n1 - A\n2 - B\n3 - C\n4 - D\n...",
            height=130
        )

    if st.button("✅ उत्तरतालिका लागू करा", type="primary"):
        if key_file:
            if key_file.name.lower().endswith(".pdf"):
                if not gemini_api_key.strip():
                    st.error("उत्तरतालिका PDF वाचण्यासाठी कृपया पायरी १ मध्ये वैध Gemini API Key टाका.")
                else:
                    with st.spinner("Gemini AI द्वारे उत्तरतालिका PDF वाचली जात आहे..."):
                        ans_dict = extract_answer_key_from_pdf(key_file, gemini_api_key.strip())
                        if ans_dict:
                            count = apply_answer_key_dict(ans_dict)
                            st.success(f"उत्तरतालिका PDF मधून एकूण {count} प्रश्नांना अचूक उत्तरे लागू झाली!")
                            st.rerun()
                        else:
                            st.error("उत्तरतालिका PDF मधील उत्तरे वाचता आली नाहीत.")
            else:
                input_text = key_file.getvalue().decode("utf-8")
                count = apply_answer_key_text(input_text)
                if count > 0:
                    st.success(f"एकूण {count} प्रश्नांना अचूक उत्तरे लागू झाली!")
                    st.rerun()

        elif key_pasted_text.strip():
            count = apply_answer_key_text(key_pasted_text.strip())
            if count > 0:
                st.success(f"एकूण {count} प्रश्नांना अचूक उत्तरे लागू झाली!")
                st.rerun()
        else:
            st.error("कृपया आधी उत्तरतालिका PDF/फाइल निवडा किंवा मजकूर पेस्ट करा.")


# --------------------------------------------------------
# 7. Summary & UI Step 3: Review & Edit Questions
# --------------------------------------------------------

if st.session_state.parsed_questions:
    st.divider()
    st.subheader("लोड केलेल्या माहितीचा सारांश")
    s1, s2, s3 = st.columns(3)
    with s1:
        st.metric("एकूण प्रश्न", len(st.session_state.parsed_questions))
    with s2:
        st.metric("भाषा मोड", st.session_state.paper_info.get("language", "EN_MR"))
    with s3:
        st.metric("वर्ष", st.session_state.paper_info.get("year", 2026))

    st.divider()
    st.header("पायरी ३ : प्रश्नांचे परीक्षण व संपादन (Review & Edit)")

    subject_dict = {s["id"]: s["name"] for s in st.session_state.subjects}
    subject_dict[-1] = "➕ नवीन विषय जोडा"

    for i, q in enumerate(st.session_state.parsed_questions):
        sub_name = subject_dict.get(q.get("subject_id"), "अवर्गीकृत")

        # SAFE STRING EXTRACTION FIX TO PREVENT 'NoneType' object has no attribute 'strip'
        raw_corr = q.get("correct_option")
        cur_corr = str(raw_corr).strip().upper() if raw_corr is not None else ""

        corr_str = f" | उत्तर: {cur_corr}" if cur_corr else ""
        lang_badge = f" [{q.get('question_text_language', 'EN_MR')}]"
        title = f"प्र. {q['question_number']} [{sub_name}]{corr_str}{lang_badge} - {str(q.get('question_text', ''))[:60]}..."

        with st.expander(title, expanded=False):
            # Question Statement & Question Diagram
            q["question_text"] = st.text_area("प्रश्न विधान", value=str(q.get("question_text", "")), height=120, key=f"q_{i}")
            st.caption(f"स्रोत भाषा: {q.get('question_text_language', 'EN_MR')} (EN = फक्त इंग्रजी, MR = फक्त मराठी, EN_MR = दोन्ही)")
            q["question_image"] = st.text_input("प्रश्नाची आकृती / इमेज URL (`question_image`)", value=str(q.get("question_image") or ""), key=f"q_img_{i}")

            # Options
            c_opt1, c_opt2 = st.columns(2)
            with c_opt1:
                q["option_a"] = st.text_input("पर्याय १ (A)", value=str(q.get("option_a", "")), key=f"a_{i}")
                q["option_c"] = st.text_input("पर्याय ३ (C)", value=str(q.get("option_c", "")), key=f"c_{i}")
            with c_opt2:
                q["option_b"] = st.text_input("पर्याय २ (B)", value=str(q.get("option_b", "")), key=f"b_{i}")
                q["option_d"] = st.text_input("पर्याय ४ (D)", value=str(q.get("option_d", "")), key=f"d_{i}")

            # Correct Answer, Difficulty & Subject Selection
            m_col1, m_col2, m_col3 = st.columns(3)

            opts_corr = ["", "A", "B", "C", "D"]
            corr_idx = opts_corr.index(cur_corr) if cur_corr in opts_corr else 0

            diff_opts = ["EASY", "MEDIUM", "HARD"]
            raw_diff = q.get("difficulty")
            cur_diff = str(raw_diff).strip().upper() if raw_diff is not None else "MEDIUM"
            diff_idx = diff_opts.index(cur_diff) if cur_diff in diff_opts else 1

            with m_col1:
                q["correct_option"] = st.selectbox("अचूक उत्तर पर्याय", opts_corr, index=corr_idx, key=f"correct_{i}")
            with m_col2:
                q["difficulty"] = st.selectbox("काठीण्य पातळी", diff_opts, index=diff_idx, key=f"diff_{i}")
            with m_col3:
                cur_sub = q.get("subject_id")
                sub_keys = list(subject_dict.keys())
                sub_idx = sub_keys.index(cur_sub) if cur_sub in sub_keys else 0
                subject_id = st.selectbox("मुख्य विषय", options=sub_keys, format_func=lambda x: subject_dict[x], index=sub_idx, key=f"sub_{i}")
                q["subject_id"] = subject_id if subject_id != -1 else None

            # Dynamic Topics Assignment
            if subject_id != -1 and subject_id is not None:
                topics = [t for t in st.session_state.topics if t["subject_id"] == subject_id]
                topic_dict = {t["id"]: t["name"] for t in topics}

                if topic_dict:
                    top_keys = list(topic_dict.keys())
                    cur_top = q.get("topic_id")
                    top_idx = top_keys.index(cur_top) if cur_top in top_keys else 0
                    q["topic_id"] = st.selectbox("उपघटक (Topic)", options=top_keys, format_func=lambda x: topic_dict[x], index=top_idx, key=f"top_{i}")
                else:
                    st.warning("या विषयासाठी उपघटक उपलब्ध नाहीत.")
                    q["topic_id"] = None
            else:
                q["new_subject_name"] = st.text_input("नवीन विषयाचे नाव", value=str(q.get("new_subject_name", "")), key=f"n_sub_{i}")
                q["new_topic_name"] = st.text_input("नवीन उपघटकाचे नाव", value=str(q.get("new_topic_name", "")), key=f"n_top_{i}")

            # Explanations & Images
            q["explanation"] = st.text_area("स्पष्टीकरण (English [[MR]] Marathi)", value=str(q.get("explanation", "")), height=70, key=f"exp_{i}")
            q["explanation_detail"] = st.text_area("सविस्तर स्पष्टीकरण (English [[MR]] Marathi)", value=str(q.get("explanation_detail", "")), height=100, key=f"exp_det_{i}")

            e_img_col1, e_ref_col2 = st.columns(2)
            with e_img_col1:
                q["explanation_image1"] = st.text_input("स्पष्टीकरणाची आकृती / इमेज URL (`explanation_image1`)", value=str(q.get("explanation_image1") or ""), key=f"exp_img_{i}")
            with e_ref_col2:
                q["reference"] = st.text_input("संदर्भ (Reference)", value=str(q.get("reference", "")), key=f"ref_{i}")


# --------------------------------------------------------
# 8. UI Step 4: Export Updated JSON File
# --------------------------------------------------------

if st.session_state.parsed_questions:
    st.divider()
    st.header("पायरी ४ : अद्ययावत JSON जतन व डाऊनलोड करा")

    if st.button("💾 अंतिम JSON फाईल तयार करा व डाऊनलोड करा", type="primary", use_container_width=True):
        subjects = list(st.session_state.subjects)
        topics = list(st.session_state.topics)

        next_subject_id = max([s["id"] for s in subjects], default=0) + 1
        next_topic_id = max([t["id"] for t in topics], default=0) + 1

        exported_questions = []

        for q in st.session_state.parsed_questions:
            subject_id = q.get("subject_id")
            topic_id = q.get("topic_id")

            if str(q.get("new_subject_name", "")).strip():
                subject_name = str(q["new_subject_name"]).strip()
                existing = next((s for s in subjects if s["name"].lower() == subject_name.lower()), None)

                if existing:
                    subject_id = existing["id"]
                else:
                    subject_id = next_subject_id
                    subjects.append({
                        "id": subject_id,
                        "name": subject_name,
                        "description": "",
                        "color_hex": "#607D8B",
                        "icon": "book",
                        "order": len(subjects) + 1
                    })
                    next_subject_id += 1

                if str(q.get("new_topic_name", "")).strip():
                    topic_name = str(q["new_topic_name"]).strip()
                    existing_topic = next((t for t in topics if t["subject_id"] == subject_id and t["name"].lower() == topic_name.lower()), None)

                    if existing_topic:
                        topic_id = existing_topic["id"]
                    else:
                        topic_id = next_topic_id
                        topics.append({
                            "id": topic_id,
                            "subject_id": subject_id,
                            "name": topic_name,
                            "description": "",
                            "order": 0
                        })
                        next_topic_id += 1

            q_img = q.get("question_image")
            q_img_val = str(q_img).strip() if q_img and str(q_img).strip() else None

            e_img = q.get("explanation_image1")
            e_img_val = str(e_img).strip() if e_img and str(e_img).strip() else None

            # Per-field null-language values: if a field's detected language is
            # "EN" only, store it under question_text/option_* as English text
            # (language metadata says EN) -- the field itself is never
            # fabricated into a language that wasn't in the source. Downstream
            # consumers can check "<field>_language" to know whether to treat
            # the value as English-only, Marathi-only, or bilingual, and can
            # render/query the "missing" side as null based on that flag.
            exported_questions.append({
                "id": None,
                "subject_id": subject_id,
                "topic_id": topic_id,
                "year": st.session_state.paper_info["year"],
                "paper_number": st.session_state.paper_info["paper_number"],
                "paper_stage": st.session_state.paper_info["paper_stage"],
                "exam_type": st.session_state.paper_info["exam_type"],
                "question_number": q["question_number"],
                "question_text": q["question_text"],
                "question_image": q_img_val,
                "option_a": q["option_a"],
                "option_b": q["option_b"],
                "option_c": q["option_c"],
                "option_d": q["option_d"],
                "correct_option": q["correct_option"],
                "difficulty": q["difficulty"],
                "reference": q["reference"],
                "explanation": q["explanation"],
                "explanation_detail": q["explanation_detail"],
                "explanation_image1": e_img_val
            })

        final_json = {
            "generated_at": datetime.now().isoformat(),
            "exam_type": st.session_state.paper_info["exam_type"],
            "paper_stage": st.session_state.paper_info["paper_stage"],
            "year": st.session_state.paper_info["year"],
            "paper_number": st.session_state.paper_info["paper_number"],
            "paper_label": st.session_state.paper_info["paper_label"],
            "questions": exported_questions
        }

        # FIX: one subject per line, one topic per line, one question per
        # line — instead of the default indent=2 pretty-printer, which spreads
        # every field of every object across its own line and makes the file
        # hard to scan/search record-by-record.
        json_string = build_one_line_per_record_json(final_json)
        filename = f"{st.session_state.paper_info['exam_type']}_{st.session_state.paper_info['paper_stage']}_{st.session_state.paper_info['year']}_P{st.session_state.paper_info['paper_number']}.json"

        st.download_button(
            label="⬇ डाऊनलोड करा (Updated JSON File)",
            data=json_string,
            file_name=filename,
            mime="application/json"
        )

        st.success(f"एकूण {len(exported_questions)} प्रश्नांसह अंतिम JSON यशस्वीरीत्या तयार झाली!")

        with st.expander("JSON फॉरमॅटचे पूर्वदृश्य (Preview)"):
            st.code(json_string[:3000], language="json")
