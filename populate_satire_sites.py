# populate_satire_sites.py
"""
Script to populate the satire_parody_sites table in Supabase
Run this from Replit after creating the table in Supabase

Prerequisites:
1. Create the table in Supabase SQL Editor (see SQL below)
2. Set environment variables: SUPABASE_URL, SUPABASE_KEY
3. Run: python populate_satire_sites.py
"""

import os
from datetime import datetime
from typing import List, Dict

# You may need to install: pip install supabase
from supabase import create_client, Client


# ===========================================
# DATA: Satire/Parody/Fake News Sites
# ===========================================

SATIRE_SITES_DATA = [
  {
    "domain": "latma.org.il",
    "name": "Latma",
    "country": "Israel",
    "language": "Hebrew",
    "category": "Satire",
    "description": "Israeli satirical news-site and weekly mock-news show: satire of media, politics and public discourse in Israel."  
  },
  {
    "domain": "panarabiaenquirer.com",
    "name": "The Pan-Arabia Enquirer",
    "country": "Middle East / pan-Arab (English-language)",
    "language": "English",
    "category": "Satire",
    "description": "‘Middle-East’s answer to The Onion’ — satirical takes on regional politics, society and current affairs." 
  },
  {
    "domain": "fognews.ru",
    "name": "FogNews",
    "country": "Russia / Russian-language region",
    "language": "Russian",
    "category": "Satire / Fake-news style",
    "description": "Russian-language satire / fake-news-style site publishing humorous / absurd news-style articles." 
  },
  {
    "domain": "the-exile.ru",
    "name": "The eXile",
    "country": "Russia / Russian-language region",
    "language": "Russian / English",  
    "category": "Satire / Parody",
    "description": "Online magazine with satirical, irreverent journalism — mixing satire, commentary and parody-news style content."  
  }
]


def get_supabase_client() -> Client:
    """
    Initialize Supabase client from environment variables
    """
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        raise ValueError(
            "❌ Missing Supabase credentials!\n"
            "Please set these environment variables in Replit Secrets:\n"
            "  - SUPABASE_URL\n"
            "  - SUPABASE_KEY"
        )
    
    return create_client(supabase_url, supabase_key)


def populate_satire_sites(client: Client, data: List[Dict]) -> Dict:
    """
    Insert satire sites into Supabase table
    
    Args:
        client: Supabase client
        data: List of site dictionaries
        
    Returns:
        Summary of results
    """
    results = {
        "success": 0,
        "failed": 0,
        "errors": []
    }
    
    print(f"\n📥 Inserting {len(data)} sites into satire_parody_sites table...\n")
    
    for site in data:
        try:
            # Use upsert to handle duplicates (updates if domain exists)
            response = client.table('satire_parody_sites').upsert(
                site,
                on_conflict='domain'
            ).execute()
            
            if response.data:
                results["success"] += 1
                print(f"  ✅ {site['name']} ({site['domain']})")
            else:
                results["failed"] += 1
                results["errors"].append(f"{site['domain']}: No data returned")
                print(f"  ⚠️ {site['name']} - No data returned")
                
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{site['domain']}: {str(e)}")
            print(f"  ❌ {site['name']} - Error: {e}")
    
    return results


def check_table_exists(client: Client) -> bool:
    """
    Check if the satire_parody_sites table exists
    """
    try:
        # Try to select from the table
        response = client.table('satire_parody_sites').select('id').limit(1).execute()
        return True
    except Exception as e:
        if 'does not exist' in str(e).lower() or '42P01' in str(e):
            return False
        # Other errors might mean table exists but has issues
        print(f"⚠️ Warning checking table: {e}")
        return True


def main():
    """
    Main function to run the population script
    """
    print("=" * 60)
    print("🎭 Satire/Parody Sites Database Population Script")
    print("=" * 60)
    
    # Step 1: Initialize Supabase client
    print("\n1️⃣ Connecting to Supabase...")
    try:
        client = get_supabase_client()
        print("   ✅ Connected successfully!")
    except ValueError as e:
        print(f"\n{e}")
        return
    except Exception as e:
        print(f"\n❌ Failed to connect to Supabase: {e}")
        return
    
    # Step 2: Check if table exists
    print("\n2️⃣ Checking if table exists...")
    if not check_table_exists(client):
        print("\n❌ Table 'satire_parody_sites' does not exist!")
        print("\nPlease create it first by running this SQL in Supabase SQL Editor:")
        print("-" * 60)
        print(CREATE_TABLE_SQL)
        print("-" * 60)
        return
    print("   ✅ Table exists!")
    
    # Step 3: Populate the table
    print("\n3️⃣ Populating table...")
    results = populate_satire_sites(client, SATIRE_SITES_DATA)
    
    # Step 4: Print summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"   ✅ Successfully inserted/updated: {results['success']}")
    print(f"   ❌ Failed: {results['failed']}")
    
    if results['errors']:
        print("\n   Errors:")
        for error in results['errors']:
            print(f"      - {error}")
    
    print("\n✨ Done!")


# SQL to create the table (for reference)
CREATE_TABLE_SQL = """
-- Create satire_parody_sites table
CREATE TABLE satire_parody_sites (
    id BIGSERIAL PRIMARY KEY,
    domain TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    country TEXT,
    language TEXT,
    category TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX idx_satire_parody_sites_domain ON satire_parody_sites(domain);
CREATE INDEX idx_satire_parody_sites_category ON satire_parody_sites(category);

-- Enable RLS (optional)
ALTER TABLE satire_parody_sites ENABLE ROW LEVEL SECURITY;

-- Allow read access
CREATE POLICY "Allow read access" ON satire_parody_sites
    FOR SELECT USING (true);
"""


if __name__ == "__main__":
    main()
