import streamlit as st
import database
import processor
from streamlit_agraph import agraph, Node, Edge, Config

st.set_page_config(layout="wide", page_title="Document Auditor")

# Custom CSS to reduce whitespace and title size
st.markdown("""
<style>
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 0rem !important;
    }
    h1 {
        font-size: 1.8rem !important;
        margin-top: 0rem !important;
        margin-bottom: 1rem !important;
    }
    .sticky-header {
        position: fixed;
        top: 2.7rem;
        left: 20.2rem;
        z-index: 80;
        background-color: rgba(255, 255, 255, 0.8);
        width: fit-content;
        padding: 5px 15px;
        border-radius: 8px;
        font-size: 1.8rem;
        font-weight: 600;
        backdrop-filter: blur(4px);
        margin-bottom: 1rem;
    }
    
    iframe {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        background-color: #fafafa;
    }
    
    /* Sidebar specific adjustments */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0rem;
        padding-top: 0rem;
    }
    
    [data-testid="stSidebar"] .block-container {
        padding-top: 0rem !important;
    }

    [data-testid="stSidebar"] h1 {
        margin-top: -2.6rem !important;
    }
</style>
""", unsafe_allow_html=True)

def main():
    st.sidebar.title("Doc Auditor")
    
    # Initialize DB (idempotent)
    database.init_db()

    # --- SIDEBAR ACTIONS ---
    if st.sidebar.button("🔄 Escanear Documentos"):
        with st.spinner("Procesando documentos..."):
            processor.scan_directory()
        st.success("Escaneo completado!")
        st.rerun()

    view_mode = st.sidebar.radio("Vista", ["Arbol de Dependencias", "Lectura Inteligente / Auditoría"])

    # --- GRAPH VIEW ---
    if view_mode == "Arbol de Dependencias":
        st.markdown('<div class="sticky-header">Arbol de Dependencias</div>', unsafe_allow_html=True)
        
        show_ghosts = st.sidebar.checkbox("Mostrar documentos no disponibles", value=True)

        docs, dependencies = database.get_dependencies_graph()
        
        if not docs:
            st.warning("No hay documentos en la base de datos. Por favor pon archivos .txt en la carpeta 'documentos' y dale a 'Escanear'.")
            return

        nodes = []
        edges = []
        added_node_ids = set()
        
        # Add Nodes
        for doc_id, filename in docs:
            nodes.append(Node(id=filename, label=filename, size=25, shape="dot"))
            added_node_ids.add(filename)
            
        # Add Edges
        for child_id, parent_id, ref_name in dependencies:
            child_name = next((d[1] for d in docs if d[0] == child_id), "Unknown")
            
            if parent_id:
                parent_name = next((d[1] for d in docs if d[0] == parent_id), "Unknown")
                edges.append(Edge(source=child_name, target=parent_name, label="depende de"))
            elif show_ghosts:
                # Create a ghost node for the unresolved reference
                # Check duplication first
                if ref_name not in added_node_ids:
                    nodes.append(Node(id=ref_name, label=ref_name + " (?)", color="gray"))
                    added_node_ids.add(ref_name)
                    
                edges.append(Edge(source=child_name, target=ref_name, label="refiere a"))

        # Physics / Animation Toggle
        # If checked: Stabilization False (Show animation)
        # If unchecked: Stabilization True (Show static / pre-calculated)
        use_physics = st.sidebar.checkbox("Mostrar animación de nodos", value=True)

        physics_config = {
            "enabled": True, # Always enable physics so layout happens
            "stabilization": {
                "enabled": not use_physics, # High stabilization = appear static. Low/None = animate.
                "iterations": 200,
                "fit": True
            }
        }

        config = Config(
            width=1200, 
            height=800, 
            directed=True, 
            nodeHighlightBehavior=True, 
            highlightColor="#F7A7A6", 
            collapsible=False, 
            fit=True,
            physics=physics_config
        )
        
        # Render Graph
        return_value = agraph(nodes=nodes, edges=edges, config=config)
        
        # Interaction (Simulated double click via selection)
        if return_value:
            st.info(f"Seleccionaste: {return_value}")
            if st.button("🔍 Auditar este documento"):
                st.session_state['selected_doc'] = return_value
                # Force switch via query param or just simple state text (State is cleaner but radio sync is hard in pure streamlit without rerun hack)
                st.write("Cambia a la vista 'Lectura Inteligente' para ver detalles.")

    # --- AUDIT VIEW ---
    elif view_mode == "Lectura Inteligente / Auditoría":
        st.title("Lectura Inteligente y Auditoría")
        
        all_docs = database.get_all_docs()
        doc_options = {d[1]: d[0] for d in all_docs}
        
        # Pre-select if clicked in graph
        default_index = 0
        if 'selected_doc' in st.session_state and st.session_state['selected_doc'] in doc_options:
             default_index = list(doc_options.keys()).index(st.session_state['selected_doc'])
        
        selected_filename = st.selectbox("Seleccionar Documento para Auditar", list(doc_options.keys()), index=default_index)
        
        if selected_filename:
            doc_id = doc_options[selected_filename]
            doc_data = database.get_doc_by_id(doc_id) # id, filename, content
            child_content = doc_data[2]
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📄 Contenido y Análisis")
                
                # Analyze structure
                struct = processor.analyze_document_structure(child_content)
                
                st.markdown("### Resumen General")
                st.info(struct["general_summary"] or "No se pudo generar un resumen.")
                
                st.markdown("### Secciones Detectadas")
                for i, section in enumerate(struct["sections"]):
                    with st.expander(f"{section['title']} ({len(section['content'])} chars)"):
                        st.markdown("**Resumen de la sección:**")
                        st.markdown(f"_{section['summary']}_")
                        st.markdown("**Contenido:**")
                        st.text_area("Texto", section['content'], height=200, key=f"{section['title']}_{doc_id}_{i}")
                
            with col2:
                st.subheader("🛡️ Reporte de Auditoría")
                
                # Get Parents
                parents = database.get_parent_docs(doc_id)
                
                if not parents:
                    st.info("Este documento no parece depender de otros (o no se encontraron referencias).")
                
                for p_id, p_filename in parents:
                    st.write(f"---")
                    st.subheader(f"Rector: {p_filename}")
                    
                    # Check connection
                    st.success("✅ Documento Rector encontrado en sistema.")
                    
                    # Get Rules from Parent
                    rules = database.get_rules_for_doc(p_id)
                    if not rules:
                        st.warning("⚠️ No se extrajeron reglas claras de este documento rector.")
                    
                    for rule_text, rule_type in rules:
                        # AUDIT CHECK
                        status = processor.check_compliance(child_content, rule_text)
                        
                        icon = "⚪"
                        color = "gray"
                        msg = "Desconocido"
                        
                        if status == "MATCH":
                            icon = "🟢"
                            color = "green"
                            msg = "Cumple"
                        elif status == "PARTIAL":
                            icon = "🟡"
                            color = "orange"
                            msg = "Parcial / Ambiguo"
                        else:
                            icon = "🔴"
                            color = "red"
                            msg = "No encontrado / Incumplimiento"
                        
                        st.markdown(f"**[{rule_type}]** {rule_text}")
                        st.markdown(f":{color}[{icon} **{msg}**]")

if __name__ == "__main__":
    main()
