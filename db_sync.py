import os
import json
import pandas as pd
import streamlit as st

# We import GSheetsConnection safely to prevent failures if it is not installed locally yet.
try:
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    GSheetsConnection = None

def get_connection():
    """
    Attempts to connect to Google Sheets using Streamlit Secrets.
    Returns GSheetsConnection instance or None if not configured.
    """
    if GSheetsConnection is None:
        return None
    
    # Check if Google Sheets credentials exist in Streamlit secrets
    if "connections" in st.secrets and "gsheets" in st.secrets.connections:
        try:
            # We initialize connection with a unique name to avoid conflicts
            return st.connection("gsheets", type=GSheetsConnection)
        except Exception:
            pass
    return None

def load_data(key, default):
    """
    Loads data for a given key.
    First checks the Streamlit session state cache.
    If not cached, fetches from Google Sheets (if configured) or falls back to local JSON.
    """
    # Initialize cache in session state if not present
    if "db_cache" not in st.session_state:
        st.session_state["db_cache"] = {}
        
    # Return from session state cache if exists
    if key in st.session_state["db_cache"]:
        return st.session_state["db_cache"][key]
        
    local_filename = f"{key}.json"
    data = default
    
    # 1. Try to load local file as fallback
    if os.path.exists(local_filename):
        try:
            with open(local_filename, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
            
    # 2. Try to fetch from Google Sheets if configured
    conn = get_connection()
    if conn is not None:
        try:
            # Read worksheet "Sheet1" or default sheet
            df = conn.read(ttl=0)
            if df is not None and not df.empty and "Key" in df.columns and "Value" in df.columns:
                row = df[df["Key"] == key]
                if not row.empty:
                    val_str = str(row.iloc[0]["Value"])
                    data = json.loads(val_str)
                    
                    # Sync local file with Google Sheets data
                    try:
                        with open(local_filename, "w", encoding="utf-8") as f:
                            json.dump(data, f)
                    except Exception:
                        pass
        except Exception:
            # Silently fallback to local data if network/creds error
            pass
            
    # Save to session cache and return
    st.session_state["db_cache"][key] = data
    return data

def save_data(key, data):
    """
    Saves data for a given key.
    Updates the session cache, saves to the local JSON file, and pushes to Google Sheets.
    """
    # Update session cache
    if "db_cache" not in st.session_state:
        st.session_state["db_cache"] = {}
    st.session_state["db_cache"][key] = data
    
    local_filename = f"{key}.json"
    
    # 1. Save locally
    try:
        with open(local_filename, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass
        
    # 2. Push to Google Sheets if configured
    conn = get_connection()
    if conn is not None:
        try:
            # Read current sheet to update or insert row
            df = conn.read(ttl=0)
            val_str = json.dumps(data)
            
            if df is None or df.empty or "Key" not in df.columns or "Value" not in df.columns:
                df = pd.DataFrame([{"Key": key, "Value": val_str}])
            else:
                # Ensure correct column types
                df["Key"] = df["Key"].astype(str)
                df["Value"] = df["Value"].astype(str)
                
                if key in df["Key"].values:
                    df.loc[df["Key"] == key, "Value"] = val_str
                else:
                    new_row = pd.DataFrame([{"Key": key, "Value": val_str}])
                    df = pd.concat([df, new_row], ignore_index=True)
            
            # Write updated dataframe back to Google Sheets
            conn.update(data=df)
        except Exception:
            pass

def clear_db_cache():
    """
    Clears the memory cache to force reloading from Google Sheets / local files.
    """
    if "db_cache" in st.session_state:
        st.session_state["db_cache"] = {}
