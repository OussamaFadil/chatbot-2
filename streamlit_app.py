from __future__ import annotations

import csv
import io
import re
import unicodedata
from html import escape

import streamlit as st
from pypdf import PdfReader


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Recherche dans mes PDF",
    page_icon="🔎",
    layout="centered",
)


# ============================================================
# NORMALISATION DU TEXTE
# ============================================================

def normalize_text(text: str) -> str:
    """
    Normalise le texte pour permettre une recherche plus souple.

    Exemples :
    - Société devient societe
    - CRÉATION devient creation
    - Les espaces multiples sont supprimés
    """

    text = text.lower()

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )

    text = text.replace("’", "'")
    text = text.replace("–", "-")
    text = text.replace("—", "-")

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# DÉCOUPAGE EN PHRASES
# ============================================================

def split_into_sentences(text: str) -> list[str]:
    """
    Découpe le texte d'une page en phrases.

    Les retours à la ligne sont également utilisés lorsque
    le PDF ne contient pas une ponctuation correcte.
    """

    text = text.replace("\x00", " ")

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    sentences: list[str] = []

    paragraphs = re.split(
        r"\n+",
        text,
    )

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        paragraph_sentences = re.split(
            r"(?<=[.!?;:])\s+",
            paragraph,
        )

        for sentence in paragraph_sentences:
            sentence = sentence.strip()

            if len(sentence) >= 2:
                sentences.append(sentence)

    return sentences


# ============================================================
# EXTRACTION DES PDF
# ============================================================

@st.cache_data(
    show_spinner=False,
)
def extract_pdf_sentences(
    filename: str,
    file_content: bytes,
) -> tuple[list[dict], int]:
    """
    Extrait toutes les phrases d'un fichier PDF.

    Le résultat est mis en cache afin d'éviter de relire le PDF
    à chaque interaction.
    """

    try:
        reader = PdfReader(
            io.BytesIO(file_content)
        )

    except Exception as error:
        raise ValueError(
            f"Impossible de lire le fichier « {filename} » : {error}"
        ) from error

    extracted_sentences: list[dict] = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        try:
            page_text = page.extract_text() or ""

        except Exception:
            page_text = ""

        sentences = split_into_sentences(
            page_text
        )

        for sentence_number, sentence in enumerate(
            sentences,
            start=1,
        ):
            extracted_sentences.append(
                {
                    "file": filename,
                    "page": page_number,
                    "position": sentence_number,
                    "sentence": sentence,
                    "normalized_sentence": normalize_text(
                        sentence
                    ),
                }
            )

    return extracted_sentences, len(reader.pages)


# ============================================================
# MOTS-CLÉS
# ============================================================

def parse_keywords(
    query: str,
) -> list[str]:
    """
    Transforme la saisie en liste de mots-clés.

    L'utilisateur peut écrire :

    création, société, 2018

    ou simplement :

    création société 2018
    """

    query = normalize_text(query)

    if "," in query:
        keywords = [
            keyword.strip()
            for keyword in query.split(",")
            if keyword.strip()
        ]

    else:
        keywords = [
            word.strip()
            for word in query.split()
            if word.strip()
        ]

    # Retirer les doublons tout en conservant l'ordre.
    return list(
        dict.fromkeys(keywords)
    )


# ============================================================
# RECHERCHE
# ============================================================

def sentence_matches(
    normalized_sentence: str,
    query: str,
    mode: str,
) -> tuple[bool, list[str]]:
    """
    Vérifie si une phrase correspond à la recherche.
    """

    normalized_query = normalize_text(
        query
    )

    if mode == "Expression exacte":
        matched = (
            normalized_query
            in normalized_sentence
        )

        return (
            matched,
            [normalized_query] if matched else [],
        )

    keywords = parse_keywords(
        query
    )

    if not keywords:
        return False, []

    matching_keywords = [
        keyword
        for keyword in keywords
        if keyword in normalized_sentence
    ]

    if mode == "Tous les mots-clés":
        matched = (
            len(matching_keywords)
            == len(keywords)
        )

    else:
        matched = bool(
            matching_keywords
        )

    return matched, matching_keywords


def search_sentences(
    all_sentences: list[dict],
    query: str,
    mode: str,
) -> list[dict]:
    """
    Retourne toutes les phrases correspondant à la recherche.
    """

    results: list[dict] = []
    seen: set[tuple[str, int, str]] = set()

    for item in all_sentences:
        matched, matching_keywords = sentence_matches(
            normalized_sentence=item[
                "normalized_sentence"
            ],
            query=query,
            mode=mode,
        )

        if not matched:
            continue

        duplicate_key = (
            item["file"],
            item["page"],
            item["normalized_sentence"],
        )

        if duplicate_key in seen:
            continue

        seen.add(
            duplicate_key
        )

        result = dict(item)

        result["matching_keywords"] = (
            matching_keywords
        )

        results.append(result)

    return results


# ============================================================
# EXPORT CSV
# ============================================================

def create_csv(
    results: list[dict],
) -> bytes:
    """
    Crée un fichier CSV avec toutes les phrases trouvées.
    """

    output = io.StringIO()

    writer = csv.writer(
        output,
        delimiter=";",
    )

    writer.writerow(
        [
            "Fichier",
            "Page",
            "Phrase",
            "Mots trouvés",
        ]
    )

    for result in results:
        writer.writerow(
            [
                result["file"],
                result["page"],
                result["sentence"],
                ", ".join(
                    result["matching_keywords"]
                ),
            ]
        )

    return output.getvalue().encode(
        "utf-8-sig"
    )


# ============================================================
# AFFICHAGE
# ============================================================

st.title("🔎 Recherche exacte dans mes PDF")

st.caption(
    "Le site copie toutes les phrases contenant vos mots-clés. "
    "Il n'utilise aucun LLM et n'invente aucune réponse."
)

uploaded_files = st.file_uploader(
    "Sélectionnez un ou plusieurs PDF",
    type=["pdf"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info(
        "Sélectionnez les PDF dans lesquels vous souhaitez chercher."
    )

    st.stop()


# ============================================================
# EXTRACTION DES DOCUMENTS
# ============================================================

all_sentences: list[dict] = []
document_information: list[dict] = []

with st.spinner(
    "Lecture des PDF sélectionnés..."
):
    for uploaded_file in uploaded_files:
        file_content = uploaded_file.getvalue()

        try:
            sentences, page_count = (
                extract_pdf_sentences(
                    filename=uploaded_file.name,
                    file_content=file_content,
                )
            )

            all_sentences.extend(
                sentences
            )

            document_information.append(
                {
                    "name": uploaded_file.name,
                    "pages": page_count,
                    "sentences": len(sentences),
                }
            )

        except Exception as error:
            st.error(str(error))


if not all_sentences:
    st.error(
        "Aucune phrase n'a été extraite. "
        "Les PDF sont probablement scannés sous forme d'images."
    )

    st.stop()


with st.expander(
    "Documents actuellement utilisés",
    expanded=False,
):
    for document in document_information:
        st.write(
            f"• **{document['name']}** — "
            f"{document['pages']} page(s), "
            f"{document['sentences']} phrase(s)"
        )


# ============================================================
# FORMULAIRE DE RECHERCHE
# ============================================================

search_mode = st.radio(
    "Mode de recherche",
    options=[
        "Tous les mots-clés",
        "Au moins un mot-clé",
        "Expression exacte",
    ],
    horizontal=True,
)

query = st.text_input(
    "Mots-clés ou expression",
    placeholder=(
        "Exemple : création, société, 2018"
    ),
    help=(
        "Séparez les mots-clés avec des virgules. "
        "Les accents et les majuscules sont ignorés."
    ),
)

search_button = st.button(
    "Rechercher toutes les phrases",
    type="primary",
    use_container_width=True,
)


# ============================================================
# RÉSULTATS
# ============================================================

if search_button:
    if not query.strip():
        st.warning(
            "Saisissez au moins un mot-clé."
        )

        st.stop()

    results = search_sentences(
        all_sentences=all_sentences,
        query=query,
        mode=search_mode,
    )

    st.session_state["last_results"] = (
        results
    )

    st.session_state["last_query"] = (
        query
    )

    st.session_state["last_mode"] = (
        search_mode
    )


results = st.session_state.get(
    "last_results",
)

if results is not None:
    query_used = st.session_state.get(
        "last_query",
        "",
    )

    mode_used = st.session_state.get(
        "last_mode",
        "",
    )

    st.divider()

    if not results:
        st.warning(
            "Aucune phrase ne contient les mots demandés."
        )

        st.write(
            "Essayez le mode **Au moins un mot-clé** "
            "pour voir les phrases contenant une partie des mots."
        )

    else:
        st.success(
            f"{len(results)} phrase(s) trouvée(s)"
        )

        st.caption(
            f"Recherche : « {query_used} » — Mode : {mode_used}"
        )

        csv_content = create_csv(
            results
        )

        st.download_button(
            label="Télécharger toutes les phrases en CSV",
            data=csv_content,
            file_name="resultats_recherche_pdf.csv",
            mime="text/csv",
            use_container_width=True,
        )

        for result_number, result in enumerate(
            results,
            start=1,
        ):
            with st.container(
                border=True
            ):
                st.markdown(
                    f"### Résultat {result_number}"
                )

                st.caption(
                    f"Fichier : {result['file']} — "
                    f"Page : {result['page']}"
                )

                st.markdown(
                    f"> {escape(result['sentence'])}"
                )

                if result["matching_keywords"]:
                    st.caption(
                        "Mots trouvés : "
                        + ", ".join(
                            result[
                                "matching_keywords"
                            ]
                        )
                    )