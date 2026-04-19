from supabase import create_client, Client
from app.core.config import settings

# Initialize Supabase client
# The credentials must be populated in the .env file or environment variables.
supabase_client: Client = create_client(
    supabase_url=settings.SUPABASE_URL,
    supabase_key=settings.SUPABASE_KEY
)
