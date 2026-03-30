import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.optimize import linear_sum_assignment
import time

st.set_page_config(page_title="YULfactory: 30인 동적 교대 관제", layout="wide")

# --- [1. 30인 통합 인력 풀 초기화] ---
if 'workers' not in st.session_state:
    ids = [f'W_{i+1:02d}' for i in range(30)]
    levels = ['전문가']*5 + ['숙련공']*15 + ['신입']*10
    np.random.shuffle(levels)
    
    st.session_state.workers = pd.DataFrame({
        'ID': ids,
        'Level': levels,
        'Skill_Weight': [1.2 if l == '전문가' else 1.0 if l == '숙련공' else 0.7 for l in levels],
        'Safety_Margin': [1.0 if l != '신입' else 0.5 for l in levels],
        'Condition': np.random.uniform(0.7, 1.0, 30), # 1.0이 최상, 낮을수록 위험 민감
        'Cum_Exp': [0.0] * 30,
        'Work_Time': [0.0] * 30, # 누적 근무 시간 (초 단위 시뮬레이션)
        'is_present': [True] * 30,
        'Status': ['대기'] * 30 # 대기, 근무, 휴식(퇴근)
    })
    # 작업자별 고유 색상 (시각화용)
    st.session_state.colors = {f'W_{i+1:02d}': f'hsl({i*12}, 70%, 50%)' for i in range(30)}

# --- [2. 사이드바: 실시간 상황 제어] ---
st.sidebar.header("🏬 현장 가용성 및 컨디션 제어")
if st.sidebar.button("시스템 전체 초기화"):
    st.session_state.clear()
    st.rerun()

# 특정 작업자 컨디션 강제 저하 (예외 상황 시뮬레이션)
target_worker = st.sidebar.selectbox("컨디션 저하 작업자 선택", st.session_state.workers['ID'])
if st.sidebar.button("해당 인원 컨디션 악화 (0.3)"):
    st.session_state.workers.loc[st.session_state.workers['ID'] == target_worker, 'Condition'] = 0.3

st.title("🛡️ 30인 규모 실시간 동적 교대 배정 시스템")
st.markdown("10개 부스 실시간 운영 | 30인 순환 근무 | 누적 8초 초과 시 자동 교대")

# --- [3. 동적 배정 로직] ---
placeholder = st.empty()

while True:
    with placeholder.container():
        # A. 가용 인원 필터링 (출근 중 & 8초 미만 근무 & 휴식 중 아님)
        workers = st.session_state.workers
        candidate_pool = workers[(workers['is_present']) & (workers['Work_Time'] < 8.0)]
        
        # B. 10명 선발 (이미 근무 중인 사람 우선 + 부족하면 대기자 중 선발)
        current_on_duty = workers[workers['Status'] == '근무']
        needed = 10 - len(current_on_duty)
        
        if needed > 0:
            new_picks = workers[(workers['Status'] == '대기') & (workers['Work_Time'] < 8.0)].iloc[:needed]
            for idx in new_picks.index:
                st.session_state.workers.at[idx, 'Status'] = '근무'
        
        on_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무'].iloc[:10]
        
        # C. 환경 데이터 (2x5 부스 배치)
        voc_matrix = np.random.randint(10, 100, (2, 5))
        booth_list = []
        for r in range(2):
            for c in range(5):
                booth_list.append({'ID': f'B_{len(booth_list)+1}', 'X': c+1, 'Y': 2-r, 'VOC': voc_matrix[r, c]})
        booths = pd.DataFrame(booth_list)

        # D. 최적 배치 알고리즘 (Hungarian Algorithm)
        cost_matrix = np.zeros((10, 10))
        for i in range(10):
            w = on_duty.iloc[i]
            for j in range(10):
                b = booths.iloc[j]
                # 화학/산공 융합 비용 함수
                # 컨디션이 낮을수록(부모 분모), 신입일수록(env_sens) 비용 급증
                env_sens = 2.0 if w['Level'] == '신입' else 1.0
                cost_matrix[i, j] = (env_sens * b['VOC'] + w['Cum_Exp']) / (w['Skill_Weight'] * w['Condition'])

        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        # E. 시각화 및 데이터 업데이트
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("🌐 공정 디지털 트윈 (10인 실시간 관제)")
            fig = go.Figure()
            fig.add_trace(go.Heatmap(z=voc_matrix, x=[1,2,3,4,5], y=[1,2], colorscale='RdYlGn_r', zmin=0, zmax=100, opacity=0.4))
            
            for r, c in zip(row_ind, col_ind):
                w = on_duty.iloc[r]
                b = booths.iloc[c]
                
                # 실시간 데이터 누적
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Cum_Exp'] += b['VOC'] * 0.05
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Work_Time'] += 0.5 # 루프당 시간 누적
                
                # 8초 초과 시 자동 교대 상태로 전환
                if st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Work_Time'].values[0] >= 8.0:
                    st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Status'] = '퇴근'

                fig.add_trace(go.Scatter(
                    x=[b['X']], y=[b['Y']], mode="markers+text",
                    marker=dict(size=40, color=st.session_state.colors[w['ID']], line=dict(width=3, color='white')),
                    text=[f"<b>{w['ID']}</b><br>{w['Level']}"], textposition="middle center", showlegend=False
                ))
            fig.update_layout(height=400, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

            # 대기 명단 시각화
            waiting = st.session_state.workers[st.session_state.workers['Status'] == '대기']
            st.write(f"⏳ 대기 중인 인원: {len(waiting)}명 ({', '.join(waiting['ID'].tolist()[:10])}...)")

        with col2:
            st.subheader("📊 실시간 근무 현황 (TOP 10)")
            # 근무 중인 인원 정보 요약
            display_df = st.session_state.workers[st.session_state.workers['Status'] == '근무'][['ID', 'Level', 'Work_Time', 'Cum_Exp', 'Condition']]
            display_df.columns = ['ID', '레벨', '근무시간', '노출량', '컨디션']
            st.dataframe(display_df.style.background_gradient(subset=['근무시간'], cmap='Blues').background_gradient(subset=['컨디션'], cmap='RdYlGn'))
            
            # 교대 알림
            expiring = on_duty[on_duty['Work_Time'] > 6.5]
            for _, row in expiring.iterrows():
                st.warning(f"⚠️ {row['ID']} 교대 1.5초 전 (누적: {row['Work_Time']:.1f}s)")
            
            low_cond = on_duty[on_duty['Condition'] < 0.5]
            for _, row in low_cond.iterrows():
                st.error(f"🚑 {row['ID']} 컨디션 불량! 긴급 재배치 중")

        time.sleep(0.5) # 빠른 시뮬레이션을 위해 속도 향상
        st.rerun()
