import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.optimize import linear_sum_assignment
import time

st.set_page_config(page_title="YULfactory: 통합 관제 시스템", layout="wide")

# --- [1. 데이터 초기화] ---
if 'workers' not in st.session_state:
    ids = [f'W_{i+1:02d}' for i in range(30)]
    levels = ['전문가']*5 + ['숙련공']*15 + ['신입']*10
    np.random.shuffle(levels)
    st.session_state.workers = pd.DataFrame({
        'ID': ids, 'Level': levels,
        'Skill_Weight': [1.2 if l == '전문가' else 1.0 if l == '숙련공' else 0.7 for l in levels],
        'Condition': 1.0, 'Cum_Exp': 0.0, 'Work_Time': 0.0,
        'is_present': True, 'Status': '대기'
    })
    st.session_state.colors = {f'W_{i+1:02d}': f'hsl({i*12}, 70%, 50%)' for i in range(30)}
    st.session_state.log = ["🚀 시스템 가동 시작"]

# --- [2. 사이드바: 제어 센터] ---
with st.sidebar:
    st.header("🕹️ 실시간 제어판")
    
    # 컨디션 조절 (현재 '근무' 중인 인원만 대상)
    on_duty_ids = st.session_state.workers[st.session_state.workers['Status'] == '근무']['ID'].tolist()
    target = st.selectbox("컨디션 하락 타겟 선택", on_duty_ids if on_duty_ids else ["없음"])
    if st.button("⚠️ 즉시 컨디션 저하 (0.2)"):
        if target != "없음":
            st.session_state.workers.loc[st.session_state.workers['ID'] == target, 'Condition'] = 0.2
            st.toast(f"{target} 위급 상황 발생! 다음 주기 교체 예정")

    st.divider()
    st.subheader("🏬 30인 출근 현황 관리")
    for i in range(30):
        w = st.session_state.workers.iloc[i]
        cb = st.checkbox(f"{w['ID']} ({w['Level']})", value=w['is_present'], key=f"p_{w['ID']}")
        if cb != st.session_state.workers.at[i, 'is_present']:
            st.session_state.workers.at[i, 'is_present'] = cb
            if not cb:
                st.session_state.workers.at[i, 'Status'] = '퇴근'
            st.rerun()

# --- [3. 메인 관제 로직 (Fragment 1.5초 주기)] ---
@st.fragment(run_every=1.5)
def update_dashboard():
    # A. 인력 운영 로직
    workers = st.session_state.workers
    
    # 1. 퇴출 조건 (8초 종료 / 컨디션 0.4 미만 / 미출근)
    to_exit = workers[(workers['Status'] == '근무') & 
                      ((workers['Work_Time'] >= 8.0) | (workers['Condition'] < 0.4) | (~workers['is_present']))]
    for idx in to_exit.index:
        st.session_state.workers.at[idx, 'Status'] = '퇴근'
        reason = "시간종료" if workers.at[idx, 'Work_Time'] >= 8.0 else "긴급교체"
        st.session_state.log.append(f"🚨 {workers.at[idx, 'ID']} ({reason})")

    # 2. 무한 루프 리셋
    waiting_pool = workers[(workers['Status'] == '대기') & (workers['is_present'])]
    if len(waiting_pool) < 5:
        st.session_state.workers.loc[(workers['Status'] == '퇴근') & (workers['is_present']), ['Work_Time', 'Status', 'Condition']] = [0.0, '대기', 1.0]
        st.session_state.log.append("♻️ 전체 인력 사이클 리셋")

    # 3. 투입 (항상 10명 유지)
    current_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무']
    if len(current_duty) < 10:
        needed = 10 - len(current_duty)
        available = st.session_state.workers[(st.session_state.workers['Status'] == '대기') & (workers['is_present'])].sort_values('Cum_Exp')
        for idx in available.iloc[:needed].index:
            st.session_state.workers.at[idx, 'Status'] = '근무'

    # B. 환경 데이터 및 최적 배정 (2x5 부스)
    on_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무'].head(10)
    
    if len(on_duty) == 10:
        voc_matrix = np.random.randint(10, 100, (2, 5))
        # 부스 좌표 생성
        booths = []
        for r in range(2):
            for c in range(5):
                booths.append({'X': c+1, 'Y': 2-r, 'VOC': voc_matrix[r, c]})
        
        # 헝가리안 알고리즘 비용 계산
        cost_matrix = np.zeros((10, 10))
        for i in range(10):
            w = on_duty.iloc[i]
            for j in range(10):
                b = booths[j]
                env_sens = 2.0 if w['Level'] == '신입' else 1.0
                cost_matrix[i, j] = (env_sens * b['VOC'] + w['Cum_Exp']) / (w['Skill_Weight'] * w['Condition'])
        
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        # C. 화면 구성 (단일 맵 집중형)
        col_left, col_right = st.columns([2.5, 1])
        
        with col_left:
            st.subheader("🌐 실시간 2x5 공정 디지털 트윈")
            fig = go.Figure()
            # 배경 히트맵 (유해물질 농도)
            fig.add_trace(go.Heatmap(z=voc_matrix, x=[1,2,3,4,5], y=[1,2], colorscale='RdYlGn_r', zmin=0, zmax=100, opacity=0.4, showscale=True))
            
            # 배정된 작업자 표시
            for i in range(len(row_ind)):
                w = on_duty.iloc[row_ind[i]]
                b = booths[col_ind[i]]
                # 데이터 실시간 누적
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Work_Time'] += 0.5
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Cum_Exp'] += b['VOC'] * 0.02
                
                border = 'red' if w['Condition'] < 0.5 else 'white'
                fig.add_trace(go.Scatter(
                    x=[b['X']], y=[b['Y']], mode="markers+text",
                    marker=dict(size=48, color=st.session_state.colors[w['ID']], line=dict(width=4, color=border)),
                    text=[f"<b>{w['ID']}</b><br>{round(w['Work_Time'],1)}s"], textposition="middle center", showlegend=False
                ))
            fig.update_layout(height=450, margin=dict(l=10, r=10, t=10, b=10), xaxis=dict(dtick=1), yaxis=dict(dtick=1))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        with col_right:
            st.subheader("📋 실시간 통합 로그")
            for l in st.session_state.log[-6:]:
                st.caption(l)
            st.divider()
            st.subheader("📊 근무자 상태 데이터")
            status_df = on_duty[['ID', 'Level', 'Condition', 'Work_Time']].copy()
            status_df['Condition'] = status_df['Condition'].round(2)
            st.dataframe(status_df.sort_values('Work_Time', ascending=False), hide_index=True)
    else:
        st.error("🚨 가용 인력 부족 (10명 미만)! 사이드바에서 출근 체크를 확인해 주세요.")

st.title("🛡️ 자동차 도장공정: 30인 지능형 교대 관제")
update_dashboard()
