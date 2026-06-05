-- Add user_id to profiles — links each profile to a Supabase Auth user
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE;

-- Enable RLS on all three tables
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenders ENABLE ROW LEVEL SECURITY;

-- Profiles: each user can only see and edit their own profile
CREATE POLICY "Users can view own profile"
    ON profiles FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own profile"
    ON profiles FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own profile"
    ON profiles FOR UPDATE USING (auth.uid() = user_id);

-- Recommendations: scoped through the user's profile
CREATE POLICY "Users can view own recommendations"
    ON recommendations FOR SELECT
    USING (profile_id IN (SELECT id FROM profiles WHERE user_id = auth.uid()));

CREATE POLICY "Users can update own recommendations"
    ON recommendations FOR UPDATE
    USING (profile_id IN (SELECT id FROM profiles WHERE user_id = auth.uid()));

-- Tenders: public read — scraper writes via service role key which bypasses RLS
CREATE POLICY "Tenders are publicly readable"
    ON tenders FOR SELECT USING (true);
