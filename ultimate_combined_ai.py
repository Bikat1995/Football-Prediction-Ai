#!/usr/bin/env python3
"""
ULTIMATE COMBINED FOOTBALL BETTING AI
Combines scattered CSV data + yearly folders + extras for MAXIMUM POWER
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import warnings
import os
warnings.filterwarnings('ignore')

# Machine Learning imports
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
from sklearn.preprocessing import StandardScaler

print('🚀 ULTIMATE COMBINED FOOTBALL BETTING AI')
print('💪 MAXIMUM POWER: Scattered + Yearly + Extras Data')

# ============================================================================
# LOAD ALL DATA SOURCES
# ============================================================================

def load_scattered_data():
    """Load scattered CSV files"""
    print("📊 Loading scattered CSV files...")
    scattered_data = {}
    
    # Load main files
    files_to_load = {
        'games': 'games.csv',
        'teams': 'teams.csv', 
        'teamstats': 'teamstats.csv',
        'appearances': 'appearances.csv',
        'shots': 'shots.csv',
        'leagues': 'leagues.csv'
    }
    
    for name, filename in files_to_load.items():
        try:
            df = pd.read_csv(filename)
            scattered_data[name] = df
            print(f"  ✅ {filename}: {len(df)} rows")
        except Exception as e:
            print(f"  ⚠️ Could not load {filename}: {e}")
            scattered_data[name] = None
    
    return scattered_data

def load_yearly_data():
    """Load data from yearly directories"""
    print("📁 Loading yearly directories...")
    all_data = []
    
    years = [str(year) for year in range(2017, 2026)]
    for year in years:
        year_path = f"c:\\Users\\HP\\Desktop\\Backtesting\\{year}"
        if os.path.exists(year_path):
            for file in os.listdir(year_path):
                if file.endswith('.csv'):
                    file_path = os.path.join(year_path, file)
                    try:
                        for encoding in ['utf-8', 'latin1', 'cp1252']:
                            try:
                                df = pd.read_csv(file_path, encoding=encoding)
                                df['source'] = 'yearly'
                                df['source_year'] = year
                                df['source_file'] = file
                                all_data.append(df)
                                print(f"  ✅ {year}/{file}: {len(df)} matches")
                                break
                            except UnicodeDecodeError:
                                continue
                    except Exception as e:
                        print(f"  ❌ Error with {file}: {e}")
    
    return all_data

def load_extras_data():
    """Load data from extras folder"""
    print("📁 Loading extras...")
    extras_data = []
    extras_path = "c:\\Users\\HP\\Desktop\\Backtesting\\Extras"
    
    if os.path.exists(extras_path):
        for file in os.listdir(extras_path):
            if file.endswith('.xlsx'):
                file_path = os.path.join(extras_path, file)
                try:
                    df = pd.read_excel(file_path)
                    df['source'] = 'extras'
                    df['source_file'] = file
                    extras_data.append(df)
                    print(f"  ✅ Extras/{file}: {len(df)} matches")
                except Exception as e:
                    print(f"  ❌ Error with {file}: {e}")
    
    return extras_data

# ============================================================================
# DATA PROCESSING AND UNIFICATION
# ============================================================================

def process_scattered_data(scattered_data):
    """Process scattered data to match standard format"""
    if scattered_data['games'] is None or scattered_data['teams'] is None:
        return None
    
    games_df = scattered_data['games'].copy()
    teams_df = scattered_data['teams'].copy()
    
    # Create team name mapping
    team_mapping = dict(zip(teams_df['teamID'], teams_df['name']))
    
    # Add team names
    games_df['home_team'] = games_df['homeTeamID'].map(team_mapping)
    games_df['away_team'] = games_df['awayTeamID'].map(team_mapping)
    
    # Create result column
    def get_result(row):
        if row['homeGoals'] > row['awayGoals']:
            return 1  # Home win
        elif row['homeGoals'] == row['awayGoals']:
            return 2  # Draw
        else:
            return 0  # Away win
    
    games_df['result'] = games_df.apply(get_result, axis=1)
    games_df['home_goals'] = games_df['homeGoals']
    games_df['away_goals'] = games_df['awayGoals']
    
    # Standardize column names
    column_mapping = {
        'date': 'date',
        'home_team': 'home_team',
        'away_team': 'away_team',
        'home_goals': 'home_goals',
        'away_goals': 'away_goals',
        'result': 'result',
        'B365H': 'home_odds',
        'B365D': 'draw_odds',
        'B365A': 'away_odds'
    }
    
    games_df = games_df.rename(columns={k: v for k, v in column_mapping.items() if k in games_df.columns})
    games_df['date'] = pd.to_datetime(games_df['date'], errors='coerce')
    games_df['source'] = 'scattered'
    
    # Add additional features from scattered data
    if 'homeProbability' in games_df.columns:
        games_df['home_prob'] = games_df['homeProbability']
        games_df['draw_prob'] = games_df['drawProbability']
        games_df['away_prob'] = games_df['awayProbability']
    
    print(f"  📋 Processed scattered data: {len(games_df)} matches")
    return games_df

def process_yearly_extras_data(all_data):
    """Process yearly and extras data to match standard format"""
    if not all_data:
        return None
    
    combined_df = pd.concat(all_data, ignore_index=True)
    
    # Map columns for yearly data
    csv_mapping = {
        'Date': 'date', 'HomeTeam': 'home_team', 'AwayTeam': 'away_team',
        'FTHG': 'home_goals', 'FTAG': 'away_goals', 'FTR': 'result',
        'HS': 'home_shots', 'AS': 'away_shots', 'HST': 'home_shots_on_target',
        'AST': 'away_shots_on_target', 'HC': 'home_corners', 'AC': 'away_corners',
        'HF': 'home_fouls', 'AF': 'away_fouls', 'HY': 'home_yellow_cards',
        'AY': 'away_yellow_cards', 'HR': 'home_red_cards', 'AR': 'away_red_cards',
        'B365H': 'home_odds', 'B365D': 'draw_odds', 'B365A': 'away_odds'
    }
    
    # Map columns for extras data
    xlsx_mapping = {
        'Date': 'date', 'Home': 'home_team', 'Away': 'away_team',
        'HG': 'home_goals', 'AG': 'away_goals', 'Res': 'result',
        'PSCH': 'home_odds', 'PSCD': 'draw_odds', 'PSCA': 'away_odds'
    }
    
    # Apply appropriate mapping
    if 'HomeTeam' in combined_df.columns:
        mapping = csv_mapping
    elif 'Home' in combined_df.columns:
        mapping = xlsx_mapping
    else:
        mapping = {}
    
    combined_df = combined_df.rename(columns=mapping)
    
    # Convert result to numeric
    if 'result' in combined_df.columns:
        combined_df['result'] = combined_df['result'].map({'H': 1, 'D': 2, 'A': 0})
    
    # Convert date
    if 'date' in combined_df.columns:
        combined_df['date'] = pd.to_datetime(combined_df['date'], dayfirst=True, errors='coerce')
    
    print(f"  📋 Processed yearly/extras data: {len(combined_df)} matches")
    return combined_df

def combine_all_data(scattered_df, yearly_extras_df):
    """Combine all data sources"""
    print("🔗 Combining all data sources...")
    
    all_dfs = []
    if scattered_df is not None:
        all_dfs.append(scattered_df)
        print(f"  ✅ Added scattered data: {len(scattered_df)} matches")
    
    if yearly_extras_df is not None:
        all_dfs.append(yearly_extras_df)
        print(f"  ✅ Added yearly/extras data: {len(yearly_extras_df)} matches")
    
    if not all_dfs:
        print("❌ No data to combine!")
        return None
    
    combined_df = pd.concat(all_dfs, ignore_index=True)
    print(f"  🎯 Total combined data: {len(combined_df)} matches")
    
    return combined_df

# ============================================================================
# ULTIMATE FEATURE ENGINEERING
# ============================================================================

class UltimateFeatureEngineer:
    def __init__(self, window=5):
        self.window = window
    
    def create_features(self, df):
        print("⚙️ Creating ultimate features...")
        df_feat = df.copy()
        
        # Basic goal features
        if 'home_goals' in df_feat.columns and 'away_goals' in df_feat.columns:
            df_feat['total_goals'] = df_feat['home_goals'] + df_feat['away_goals']
            df_feat['goal_diff'] = df_feat['home_goals'] - df_feat['away_goals']
        
        # Rolling averages for goals
        if 'home_goals' in df_feat.columns:
            df_feat = df_feat.sort_values(['home_team', 'date'])
            df_feat['home_goals_rolling'] = (
                df_feat.groupby('home_team')['home_goals']
                .transform(lambda x: x.rolling(self.window, min_periods=1).mean())
            )
            
            df_feat = df_feat.sort_values(['away_team', 'date'])
            df_feat['away_goals_rolling'] = (
                df_feat.groupby('away_team')['away_goals']
                .transform(lambda x: x.rolling(self.window, min_periods=1).mean())
            )
        
        # Rolling shots if available
        if 'home_shots' in df_feat.columns:
            df_feat = df_feat.sort_values(['home_team', 'date'])
            df_feat['home_shots_rolling'] = (
                df_feat.groupby('home_team')['home_shots']
                .transform(lambda x: x.rolling(self.window, min_periods=1).mean())
            )
            
            df_feat = df_feat.sort_values(['away_team', 'date'])
            df_feat['away_shots_rolling'] = (
                df_feat.groupby('away_team')['away_shots']
                .transform(lambda x: x.rolling(self.window, min_periods=1).mean())
            )
        
        # Form indicators
        if 'result' in df_feat.columns:
            df_feat['points'] = np.where(df_feat['result'] == 1, 3, 
                                           np.where(df_feat['result'] == 2, 1, 0))
            
            df_feat = df_feat.sort_values(['home_team', 'date'])
            df_feat['home_form'] = (
                df_feat.groupby('home_team')['points']
                .transform(lambda x: x.rolling(self.window, min_periods=1).mean())
            )
            
            df_feat = df_feat.sort_values(['away_team', 'date'])
            df_feat['away_form'] = (
                df_feat.groupby('away_team')['points']
                .transform(lambda x: x.rolling(self.window, min_periods=1).mean())
            )
        
        # Advanced odds features
        if 'home_odds' in df_feat.columns and 'away_odds' in df_feat.columns:
            df_feat['odds_ratio'] = df_feat['away_odds'] / df_feat['home_odds']
            df_feat['odds_diff'] = df_feat['away_odds'] - df_feat['home_odds']
            df_feat['implied_prob_home'] = 1 / df_feat['home_odds']
            df_feat['implied_prob_away'] = 1 / df_feat['away_odds']
            df_feat['implied_prob_draw'] = 1 / df_feat['draw_odds'] if 'draw_odds' in df_feat.columns else 0
        
        # Probability features from scattered data
        if 'home_prob' in df_feat.columns:
            df_feat['prob_diff_home_away'] = df_feat['home_prob'] - df_feat['away_prob']
            df_feat['prob_advantage'] = np.where(df_feat['home_prob'] > df_feat['away_prob'], 
                                            df_feat['home_prob'] - df_feat['away_prob'], 
                                            df_feat['away_prob'] - df_feat['home_prob'])
        
        # Advanced rolling features
        if 'home_goals_rolling' in df_feat.columns and 'away_goals_rolling' in df_feat.columns:
            df_feat['goal_diff_rolling'] = df_feat['home_goals_rolling'] - df_feat['away_goals_rolling']
            df_feat['total_goals_rolling'] = df_feat['home_goals_rolling'] + df_feat['away_goals_rolling']
        
        # Source-based features
        if 'source' in df_feat.columns:
            df_feat['is_scattered'] = (df_feat['source'] == 'scattered').astype(int)
            df_feat['is_yearly'] = (df_feat['source'] == 'yearly').astype(int)
            df_feat['is_extras'] = (df_feat['source'] == 'extras').astype(int)
        
        # Remove NaN from engineered features
        engineered_cols = [col for col in df_feat.columns if any(x in col for x in 
                        ['rolling', 'form', 'diff', 'ratio', 'implied', 'prob', 'is_'])]
        df_feat = df_feat.dropna(subset=engineered_cols)
        
        print(f"  ✅ Created {len(engineered_cols)} engineered features")
        return df_feat

# ============================================================================
# ULTIMATE MODEL TRAINING
# ============================================================================

class UltimateModel:
    def __init__(self):
        self.scaler = StandardScaler()
        self.models = {}
        self.feature_names = None
    
    def train(self, X_train, y_train, feature_names):
        print("🤖 Training ULTIMATE combined model...")
        self.feature_names = feature_names
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        
        # XGBoost with enhanced parameters
        print("  📊 Training XGBoost...")
        xgb_params = {
            'n_estimators': 500,  # More trees for combined data
            'max_depth': 8,
            'learning_rate': 0.05,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'objective': 'multi:softprob',
            'num_class': 3,
            'random_state': 42
        }
        self.models['xgb'] = xgb.XGBClassifier(**xgb_params)
        self.models['xgb'].fit(X_train_scaled, y_train)
        
        # Random Forest with enhanced parameters
        print("  🌲 Training Random Forest...")
        rf_params = {
            'n_estimators': 500,
            'max_depth': 15,
            'min_samples_split': 10,
            'min_samples_leaf': 5,
            'random_state': 42,
            'n_jobs': -1
        }
        self.models['rf'] = RandomForestClassifier(**rf_params)
        self.models['rf'].fit(X_train_scaled, y_train)
        
        # Ultimate Ensemble
        print("  🎯 Creating ULTIMATE Ensemble...")
        self.models['ensemble'] = VotingClassifier(
            estimators=[('xgb', self.models['xgb']), ('rf', self.models['rf'])],
            voting='soft'
        )
        self.models['ensemble'].fit(X_train_scaled, y_train)
        
        print("✅ ULTIMATE models trained successfully!")
    
    def evaluate(self, X_test, y_test):
        X_test_scaled = self.scaler.transform(X_test)
        y_pred = self.models['ensemble'].predict(X_test_scaled)
        
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, average='weighted')
        recall = recall_score(y_test, y_pred, average='weighted')
        f1 = f1_score(y_test, y_pred, average='weighted')
        
        print(f"\n📈 ULTIMATE Model Performance:")
        print(f"   Accuracy:  {accuracy:.3f} ({accuracy:.1%})")
        print(f"   Precision: {precision:.3f}")
        print(f"   Recall:    {recall:.3f}")
        print(f"   F1-Score:  {f1:.3f}")
        
        # Confusion matrix
        cm = confusion_matrix(y_test, y_pred)
        print(f"\n📊 Confusion Matrix:")
        print(f"   Away Win: {cm[0]}")
        print(f"   Home Win: {cm[1]}")
        print(f"   Draw:      {cm[2]}")
        
        return {'accuracy': accuracy, 'precision': precision, 'recall': recall, 'f1': f1}
    
    def save_model(self, filepath='ultimate_combined_model.pkl'):
        """Save ultimate model"""
        import joblib
        model_data = {
            'ensemble': self.models['ensemble'],
            'xgb': self.models['xgb'],
            'rf': self.models['rf'],
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'version': 'ultimate_v1.0',
            'created': datetime.now(),
            'data_sources': ['scattered', 'yearly', 'extras']
        }
        joblib.dump(model_data, filepath)
        print(f"💾 ULTIMATE model saved: {filepath}")

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    try:
        print("\n" + "="*80)
        print("🏆 ULTIMATE COMBINED FOOTBALL BETTING AI")
        print("💪 MAXIMUM POWER: Scattered + Yearly + Extras Data")
        print("="*80)
        
        # 1. Load all data sources
        print("\n📊 Step 1: Loading ALL data sources...")
        scattered_data = load_scattered_data()
        yearly_data = load_yearly_data()
        extras_data = load_extras_data()
        
        # 2. Process data sources
        print("\n🔧 Step 2: Processing data sources...")
        scattered_df = process_scattered_data(scattered_data)
        yearly_extras_df = process_yearly_extras_data(yearly_data + extras_data)
        
        # 3. Combine all data
        print("\n🔗 Step 3: Combining all data sources...")
        combined_df = combine_all_data(scattered_df, yearly_extras_df)
        
        if combined_df is None:
            print("❌ No data combined!")
            return
        
        # 4. Clean data
        print("\n🧹 Step 4: Cleaning combined data...")
        # Remove matches with missing key data
        key_cols = ['date', 'home_team', 'away_team', 'home_goals', 'away_goals', 'result']
        combined_df = combined_df.dropna(subset=[col for col in key_cols if col in combined_df.columns])
        
        # Sort by date
        combined_df = combined_df.sort_values('date').reset_index(drop=True)
        
        # Remove extreme outliers
        if 'home_goals' in combined_df.columns and 'away_goals' in combined_df.columns:
            combined_df = combined_df[(combined_df['home_goals'] <= 15) & (combined_df['away_goals'] <= 15)]
        
        # Handle infinity values
        numeric_cols = combined_df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            combined_df[col] = combined_df[col].replace([np.inf, -np.inf], np.nan)
            combined_df[col].fillna(combined_df[col].median(), inplace=True)
        
        print(f"✅ Cleaned combined data: {len(combined_df):,} matches")
        
        # 5. Ultimate feature engineering
        print("\n⚙️ Step 5: Ultimate feature engineering...")
        engineer = UltimateFeatureEngineer(window=5)
        df_features = engineer.create_features(combined_df)
        print(f"✅ Ultimate features created: {df_features.shape[1]} columns")
        
        # 6. Prepare for modeling
        print("\n📊 Step 6: Preparing data for modeling...")
        exclude_cols = ['date', 'home_team', 'away_team', 'home_goals', 'away_goals', 
                       'result', 'gameID', 'leagueID', 'season', 'source', 
                       'source_year', 'source_file', 'homeTeamID', 'awayTeamID',
                       'homeGoals', 'awayGoals', 'points']
        numeric_cols = df_features.select_dtypes(include=[np.number]).columns.tolist()
        feature_cols = [col for col in numeric_cols if col not in exclude_cols]
        
        X = df_features[feature_cols]
        y = df_features['result']
        
        # Split data (time-based split)
        split_idx = int(len(df_features) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]
        
        print(f"   Training data: {len(X_train):,} matches")
        print(f"   Test data: {len(X_test):,} matches")
        print(f"   Features: {len(feature_cols)}")
        
        # 7. Train ultimate model
        print("\n🎓 Step 7: Training ULTIMATE model...")
        model = UltimateModel()
        model.train(X_train, y_train, feature_cols)
        
        # 8. Evaluate
        print("\n📈 Step 8: Evaluating ULTIMATE model...")
        metrics = model.evaluate(X_test, y_test)
        
        # 9. Save model
        print("\n💾 Step 9: Saving ULTIMATE model...")
        model.save_model()
        
        # 10. Final summary
        print(f"\n🎉 ULTIMATE COMBINED AI TRAINING COMPLETED!")
        print("="*80)
        print(f"🏆 Final Accuracy: {metrics['accuracy']:.1%}")
        print(f"📊 Total matches processed: {len(df_features):,}")
        print(f"📁 Data sources: Scattered CSV + Yearly (2017-2025) + Extras")
        print(f"🤖 Models: Enhanced XGBoost + Random Forest + Ultimate Ensemble")
        print(f"⚙️ Features: {len(feature_cols)} ultimate engineered features")
        print(f"💾 Model saved: ultimate_combined_model.pkl")
        print("="*80)
        
        print("\n🚀 THIS IS THE MOST POWERFUL VERSION!")
        print("💡 Combines ALL your data for maximum predictive power!")
        
    except Exception as e:
        print(f"\n❌ Error during ultimate training: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
