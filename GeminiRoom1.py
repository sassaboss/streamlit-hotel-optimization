import streamlit as st
import pandas as pd
import re # Za parsiranje stringa aranžmana gostiju

# --- Callback funkcija za izmenu dostupnosti sobe ---
def toggle_room_availability_callback(room_id_to_update, checkbox_key_in_session):
    for r_idx, r_data in enumerate(st.session_state.individual_rooms):
        if r_data['id'] == room_id_to_update:
            if checkbox_key_in_session in st.session_state:
                st.session_state.individual_rooms[r_idx]['is_available'] = st.session_state[checkbox_key_in_session]
            break

def perform_allocation(total_guests, 
                       solo_non_sharing_guests_count, 
                       exclusive_couples_guest_count, 
                       room_sharing_bed_sharing_pairs_guest_count, 
                       max_price_per_guest, breakfast_chosen, lunch_chosen, dinner_chosen, 
                       individual_rooms_data, global_meal_prices_data, num_days):
    allocation = []
    
    remaining_guests_total_to_allocate = total_guests
    remaining_solo_guests = solo_non_sharing_guests_count
    remaining_exclusive_couples_guests = exclusive_couples_guest_count 
    remaining_flexible_pairs_guests = room_sharing_bed_sharing_pairs_guest_count

    meal_cost_per_guest_for_all_rooms = 0.0
    if breakfast_chosen: meal_cost_per_guest_for_all_rooms += global_meal_prices_data['breakfast']
    if lunch_chosen: meal_cost_per_guest_for_all_rooms += global_meal_prices_data['lunch']
    if dinner_chosen: meal_cost_per_guest_for_all_rooms += global_meal_prices_data['dinner']

    current_available_rooms_for_allocation = [
        room for room in individual_rooms_data if room.get('is_available', True)
    ]
    
    num_available_rooms_total_initially = len(current_available_rooms_for_allocation)
    total_available_beds_capacity = sum(
        room['single_beds'] * 1 + room['double_beds'] * 2 + room['sofa_beds'] * 2
        for room in current_available_rooms_for_allocation
    )
    avg_prices_by_guest_type_with_count_report = {
        "Solo Gost (zasebna soba)": (0, 0),
        "Ekskluzivni Par (po osobi, zasebna soba)": (0, 0),
        "Fleksibilni Par (po osobi, deli krevet i sobu)": (0, 0),
        "Individualni Gost (deli sobu, ne deli krevet)": (0, 0)
    }

    if not current_available_rooms_for_allocation:
        return [], 0.0, 0.0, 0, total_guests, "no_rooms_available", 0.0, 0, 0, \
               num_available_rooms_total_initially, total_available_beds_capacity, \
               0, 0, 0, 0.0, 0.0, avg_prices_by_guest_type_with_count_report

    processed_rooms_for_allocation = []
    num_rooms_within_budget = 0
    for r_data_orig in current_available_rooms_for_allocation:
        temp_room_data = r_data_orig.copy() 
        max_room_capacity_persons = temp_room_data['single_beds'] * 1 + temp_room_data['double_beds'] * 2 + temp_room_data['sofa_beds'] * 2
        price_per_guest_room_only_max = temp_room_data['price'] / max_room_capacity_persons if max_room_capacity_persons > 0 else float('inf')
        temp_room_data['total_price_per_guest_max_cap'] = price_per_guest_room_only_max + meal_cost_per_guest_for_all_rooms
        temp_room_data['over_max_budget'] = temp_room_data['total_price_per_guest_max_cap'] > max_price_per_guest
        if not temp_room_data['over_max_budget']: num_rooms_within_budget += 1
        temp_room_data['calculated_max_capacity_persons'] = max_room_capacity_persons
        processed_rooms_for_allocation.append(temp_room_data)

    bed_slots_for_allocation = []
    for room_data_proc in processed_rooms_for_allocation:
        bed_slots_for_allocation.append({
            'room_id': room_data_proc['id'], 'room_name': room_data_proc['name'],
            'priority': room_data_proc['priority'], 'price': room_data_proc['price'],
            'single_beds_available': room_data_proc['single_beds'], 
            'double_beds_available': room_data_proc['double_beds'],
            'sofa_beds_available': room_data_proc['sofa_beds'],
            'accommodated_guests': 0, 'room_income_this_instance': 0.0, 
            'meal_income_this_instance': 0.0, 'over_max_budget': room_data_proc['over_max_budget'], 
            'total_price_per_guest_for_room': room_data_proc['total_price_per_guest_max_cap'], 
            'calculated_max_capacity_persons': room_data_proc['calculated_max_capacity_persons'], 
            'is_taken_by_solo_or_exclusive_couple': False, 'guest_arrangement_details': [] 
        })

    # --- FAZE ALOKACIJE --- 
    if remaining_solo_guests > 0 and remaining_guests_total_to_allocate > 0:
        bed_slots_for_allocation.sort(key=lambda x: ( x['priority'], not (x['double_beds_available'] > 0 or x['sofa_beds_available'] > 0 or x['single_beds_available'] > 0), x['calculated_max_capacity_persons'] ))
        for room_instance in bed_slots_for_allocation:
            if remaining_solo_guests <= 0 or remaining_guests_total_to_allocate <= 0: break
            if room_instance['accommodated_guests'] > 0: continue 
            if room_instance['double_beds_available'] > 0 or room_instance['sofa_beds_available'] > 0 or room_instance['single_beds_available'] > 0 :
                room_instance['accommodated_guests'] = 1; room_instance['room_income_this_instance'] = room_instance['price']
                room_instance['meal_income_this_instance'] = 1 * meal_cost_per_guest_for_all_rooms
                room_instance['guest_arrangement_details'].append("1 Solo gost (cela soba)")
                remaining_solo_guests -= 1; remaining_guests_total_to_allocate -= 1
                room_instance['is_taken_by_solo_or_exclusive_couple'] = True
                room_instance['single_beds_available'] = 0; room_instance['double_beds_available'] = 0; room_instance['sofa_beds_available'] = 0
    
    if remaining_exclusive_couples_guests > 0 and remaining_guests_total_to_allocate > 0:
        bed_slots_for_allocation.sort(key=lambda x: ( x['is_taken_by_solo_or_exclusive_couple'], x['priority'], not (x['double_beds_available'] > 0 or x['sofa_beds_available'] > 0), x['calculated_max_capacity_persons'] ))
        for room_instance in bed_slots_for_allocation:
            if remaining_exclusive_couples_guests < 2 or remaining_guests_total_to_allocate < 2 : break 
            if room_instance['is_taken_by_solo_or_exclusive_couple']: continue 
            bed_type_used_for_exclusive_couple = None
            if room_instance['double_beds_available'] >= 1: bed_type_used_for_exclusive_couple = "bračni"
            elif room_instance['sofa_beds_available'] >= 1: bed_type_used_for_exclusive_couple = "sofa"
            if bed_type_used_for_exclusive_couple:
                room_instance['accommodated_guests'] = 2; room_instance['room_income_this_instance'] = room_instance['price']
                room_instance['meal_income_this_instance'] = 2 * meal_cost_per_guest_for_all_rooms
                room_instance['guest_arrangement_details'].append(f"Par x1 (zasebna soba, {bed_type_used_for_exclusive_couple})")
                remaining_exclusive_couples_guests -= 2; remaining_guests_total_to_allocate -= 2
                room_instance['is_taken_by_solo_or_exclusive_couple'] = True
                room_instance['single_beds_available'] = 0; room_instance['double_beds_available'] = 0; room_instance['sofa_beds_available'] = 0    

    if remaining_flexible_pairs_guests > 0 and remaining_guests_total_to_allocate > 0:
        bed_slots_for_allocation.sort(key=lambda x: ( x['is_taken_by_solo_or_exclusive_couple'], x['priority'], -(x['double_beds_available'] * 2), -(x['sofa_beds_available'] * 2) ))
        for room_instance in bed_slots_for_allocation:
            if remaining_guests_total_to_allocate < 2 or remaining_flexible_pairs_guests < 2: break 
            if room_instance['is_taken_by_solo_or_exclusive_couple']: continue 
            guests_added_to_room_in_this_step_pairs = 0; pairs_placed_description_this_step = []
            max_pairs_in_double = min(room_instance['double_beds_available'], remaining_flexible_pairs_guests // 2)
            if max_pairs_in_double > 0:
                guests_to_add = max_pairs_in_double * 2; room_instance['accommodated_guests'] += guests_to_add; guests_added_to_room_in_this_step_pairs += guests_to_add
                remaining_guests_total_to_allocate -= guests_to_add; remaining_flexible_pairs_guests -= guests_to_add
                room_instance['double_beds_available'] -= max_pairs_in_double; pairs_placed_description_this_step.append(f"Fleks. par(ova) x{max_pairs_in_double} (bračni)")
            if remaining_flexible_pairs_guests >= 2: 
                max_pairs_in_sofa = min(room_instance['sofa_beds_available'], remaining_flexible_pairs_guests // 2)
                if max_pairs_in_sofa > 0:
                    guests_to_add = max_pairs_in_sofa * 2; room_instance['accommodated_guests'] += guests_to_add; guests_added_to_room_in_this_step_pairs += guests_to_add
                    remaining_guests_total_to_allocate -= guests_to_add; remaining_flexible_pairs_guests -= guests_to_add
                    room_instance['sofa_beds_available'] -= max_pairs_in_sofa; pairs_placed_description_this_step.append(f"Fleks. par(ova) x{max_pairs_in_sofa} (sofa)")
            if pairs_placed_description_this_step: room_instance['guest_arrangement_details'].extend(pairs_placed_description_this_step)
            if guests_added_to_room_in_this_step_pairs > 0:
                if room_instance['room_income_this_instance'] == 0: room_instance['room_income_this_instance'] = room_instance['price']
                room_instance['meal_income_this_instance'] += guests_added_to_room_in_this_step_pairs * meal_cost_per_guest_for_all_rooms

    if remaining_guests_total_to_allocate > 0: 
        bed_slots_for_allocation.sort(key=lambda x: ( x['is_taken_by_solo_or_exclusive_couple'], 0 if x['accommodated_guests'] > 0 else 1, x['priority'], -(x['single_beds_available']), -(x['double_beds_available']), -(x['sofa_beds_available']) ))
        for room_instance in bed_slots_for_allocation:
            if remaining_guests_total_to_allocate <= 0: break
            if room_instance['is_taken_by_solo_or_exclusive_couple']: continue
            guests_added_to_room_in_this_step_individuals = 0; individuals_placed_description_this_step = [] 
            can_add_to_single = min(remaining_guests_total_to_allocate, room_instance['single_beds_available'])
            if can_add_to_single > 0:
                room_instance['accommodated_guests'] += can_add_to_single; guests_added_to_room_in_this_step_individuals += can_add_to_single
                remaining_guests_total_to_allocate -= can_add_to_single; room_instance['single_beds_available'] -= can_add_to_single
                individuals_placed_description_this_step.append(f"Pojedinac/ci x{can_add_to_single} (singl)")
            if remaining_guests_total_to_allocate <= 0: 
                if individuals_placed_description_this_step: 
                    new_desc = [d for d in individuals_placed_description_this_step if d not in room_instance['guest_arrangement_details']]
                    if new_desc: room_instance['guest_arrangement_details'].extend(new_desc)
                if guests_added_to_room_in_this_step_individuals > 0: 
                    if room_instance['room_income_this_instance'] == 0: room_instance['room_income_this_instance'] = room_instance['price']
                    room_instance['meal_income_this_instance'] += guests_added_to_room_in_this_step_individuals * meal_cost_per_guest_for_all_rooms
                break 
            can_add_to_double_ind = min(remaining_guests_total_to_allocate, room_instance['double_beds_available'])
            if can_add_to_double_ind > 0:
                room_instance['accommodated_guests'] += can_add_to_double_ind; guests_added_to_room_in_this_step_individuals += can_add_to_double_ind
                remaining_guests_total_to_allocate -= can_add_to_double_ind; room_instance['double_beds_available'] -= can_add_to_double_ind
                individuals_placed_description_this_step.append(f"Pojedinac/ci x{can_add_to_double_ind} (bračni, 1 po kr.)")
            if remaining_guests_total_to_allocate <= 0: 
                current_details_for_room = [d for d in individuals_placed_description_this_step if d not in room_instance['guest_arrangement_details']]
                if current_details_for_room: room_instance['guest_arrangement_details'].extend(current_details_for_room)
                if guests_added_to_room_in_this_step_individuals > 0: 
                    if room_instance['room_income_this_instance'] == 0: room_instance['room_income_this_instance'] = room_instance['price']
                    room_instance['meal_income_this_instance'] += guests_added_to_room_in_this_step_individuals * meal_cost_per_guest_for_all_rooms
                break
            can_add_to_sofa_ind = min(remaining_guests_total_to_allocate, room_instance['sofa_beds_available'])
            if can_add_to_sofa_ind > 0:
                room_instance['accommodated_guests'] += can_add_to_sofa_ind; guests_added_to_room_in_this_step_individuals += can_add_to_sofa_ind
                remaining_guests_total_to_allocate -= can_add_to_sofa_ind; room_instance['sofa_beds_available'] -= can_add_to_sofa_ind
                individuals_placed_description_this_step.append(f"Pojedinac/ci x{can_add_to_sofa_ind} (sofa, 1 po kr.)")
            if individuals_placed_description_this_step:
                new_desc_to_add_final_ind = [d for d in individuals_placed_description_this_step if d not in room_instance['guest_arrangement_details']]
                if new_desc_to_add_final_ind: room_instance['guest_arrangement_details'].extend(new_desc_to_add_final_ind)
            if guests_added_to_room_in_this_step_individuals > 0:
                if room_instance['room_income_this_instance'] == 0: room_instance['room_income_this_instance'] = room_instance['price']
                room_instance['meal_income_this_instance'] += guests_added_to_room_in_this_step_individuals * meal_cost_per_guest_for_all_rooms
    
    aggregated_allocation = []
    solo_effective_prices_list = []
    exclusive_couple_effective_prices_list = []
    flexible_pair_effective_prices_list = []
    individual_effective_prices_list = []

    for room_instance_final in bed_slots_for_allocation:
        if room_instance_final['accommodated_guests'] > 0:
            unique_details = []; seen = set()
            if room_instance_final['guest_arrangement_details']:
                for detail in room_instance_final['guest_arrangement_details']:
                    if detail not in seen: unique_details.append(detail); seen.add(detail)
            arrangement_desc_str = ", ".join(unique_details) if unique_details else "Nije definisano"
            effective_price_per_guest_actual = 0.0
            if room_instance_final['accommodated_guests'] > 0:
                effective_price_per_guest_actual = (room_instance_final['price'] + room_instance_final['meal_income_this_instance']) / room_instance_final['accommodated_guests']
            
            num_guests_in_room_final = room_instance_final['accommodated_guests']
            if "1 Solo gost (cela soba)" in arrangement_desc_str and num_guests_in_room_final == 1:
                solo_effective_prices_list.append(effective_price_per_guest_actual)
            elif "Par x1 (zasebna soba" in arrangement_desc_str and num_guests_in_room_final == 2:
                exclusive_couple_effective_prices_list.extend([effective_price_per_guest_actual] * 2)
            else: 
                total_flex_pair_guests_in_room_current = 0
                for match in re.finditer(r"Fleks\. par\(ova\) x(\d+)", arrangement_desc_str):
                    total_flex_pair_guests_in_room_current += int(match.group(1)) * 2
                if total_flex_pair_guests_in_room_current > 0:
                    flexible_pair_effective_prices_list.extend([effective_price_per_guest_actual] * total_flex_pair_guests_in_room_current)
                total_individual_guests_in_room_current = 0
                for match in re.finditer(r"Pojedinac/ci x(\d+)", arrangement_desc_str):
                    total_individual_guests_in_room_current += int(match.group(1))
                if total_individual_guests_in_room_current > 0:
                    individual_effective_prices_list.extend([effective_price_per_guest_actual] * total_individual_guests_in_room_current)
            
            aggregated_allocation.append({
                'room_id': room_instance_final['room_id'], 'room_name': room_instance_final['room_name'],
                'priority': room_instance_final['priority'], 'guests_accommodated': room_instance_final['accommodated_guests'],
                'room_income': room_instance_final['room_income_this_instance'], 'meal_income': room_instance_final['meal_income_this_instance'],
                'single_beds_remaining': room_instance_final['single_beds_available'], 'double_beds_remaining': room_instance_final['double_beds_available'],
                'sofa_beds_remaining': room_instance_final['sofa_beds_available'], 'room_capacity': room_instance_final['calculated_max_capacity_persons'],
                'total_price_per_guest_for_room': room_instance_final['total_price_per_guest_for_room'], 
                'effective_price_per_guest_actual': effective_price_per_guest_actual, 
                'over_max_budget': room_instance_final['over_max_budget'], 'guest_arrangement': arrangement_desc_str
            })
    
    allocation = sorted(aggregated_allocation, key=lambda x: (x['priority'], x['room_id']))

    avg_prices_by_guest_type_with_count_report = {
        "Solo Gost (zasebna soba)": (sum(solo_effective_prices_list) / len(solo_effective_prices_list) if solo_effective_prices_list else 0, len(solo_effective_prices_list)),
        "Ekskluzivni Par (po osobi, zasebna soba)": (sum(exclusive_couple_effective_prices_list) / len(exclusive_couple_effective_prices_list) if exclusive_couple_effective_prices_list else 0, len(exclusive_couple_effective_prices_list)),
        "Fleksibilni Par (po osobi, deli krevet i možda sobu)": (sum(flexible_pair_effective_prices_list) / len(flexible_pair_effective_prices_list) if flexible_pair_effective_prices_list else 0, len(flexible_pair_effective_prices_list)),
        "Individualni Gost (deli sobu, ne krevet)": (sum(individual_effective_prices_list) / len(individual_effective_prices_list) if individual_effective_prices_list else 0, len(individual_effective_prices_list))
    }

    final_total_accommodated_guests = sum(item['guests_accommodated'] for item in allocation)
    final_total_income_from_rooms = sum(item['room_income'] for item in allocation)
    final_total_income_from_meals = sum(item['meal_income'] for item in allocation)
    final_total_rooms_used_count = len(allocation) 
    total_room_income_for_num_days = final_total_income_from_rooms * num_days
    total_meal_income_for_num_days = final_total_income_from_meals * num_days
    avg_achieved_price_per_bed_room_only = final_total_income_from_rooms / final_total_accommodated_guests if final_total_accommodated_guests > 0 else 0.0
    total_hotel_capacity_beds_val = sum(room['single_beds'] * 1 + room['double_beds'] * 2 + room['sofa_beds'] * 2 for room in individual_rooms_data)
    total_physical_rooms_in_hotel_val = len(individual_rooms_data)
    avg_price_per_guest_incl_meals_val = (final_total_income_from_rooms + final_total_income_from_meals) / final_total_accommodated_guests if final_total_accommodated_guests > 0 else 0.0
    avg_price_per_occupied_room_val = final_total_income_from_rooms / final_total_rooms_used_count if final_total_rooms_used_count > 0 else 0.0
    status_msg = "unknown" 
    final_remaining_unallocated = remaining_guests_total_to_allocate 

    if total_guests == 0: status_msg = "no_guests_requested"
    elif num_available_rooms_total_initially == 0: status_msg = "no_rooms_available"
    elif final_total_accommodated_guests == 0:
        if num_rooms_within_budget == 0 and num_available_rooms_total_initially > 0: status_msg = "no_rooms_within_budget_and_no_guests"
        else: status_msg = "no_guests_accommodated"
    elif final_remaining_unallocated == 0 and final_total_accommodated_guests == total_guests: 
        all_used_rooms_over_budget_flag = False 
        if final_total_rooms_used_count > 0 : 
            all_used_rooms_over_budget_flag = True 
            for room_in_alloc in allocation:
                if not room_in_alloc['over_max_budget']: all_used_rooms_over_budget_flag = False; break
        if all_used_rooms_over_budget_flag and num_rooms_within_budget == 0 and final_total_rooms_used_count > 0 : status_msg = "all_rooms_over_budget" 
        else: status_msg = "success"
    elif final_total_accommodated_guests > 0 and final_remaining_unallocated > 0: status_msg = "partial_success"

    return (allocation, final_total_income_from_rooms, final_total_income_from_meals, 
            final_total_accommodated_guests, final_remaining_unallocated, status_msg, 
            avg_achieved_price_per_bed_room_only, final_total_rooms_used_count, 
            num_rooms_within_budget, 
            num_available_rooms_total_initially, 
            total_available_beds_capacity, 
            total_hotel_capacity_beds_val, avg_price_per_guest_incl_meals_val, 
            avg_price_per_occupied_room_val, total_physical_rooms_in_hotel_val,
            total_room_income_for_num_days, total_meal_income_for_num_days,
            avg_prices_by_guest_type_with_count_report 
            )

# --- Glavna aplikacija ---
def main():
    ALLOCATION_TABLE_HEIGHT = st.session_state.get('allocation_table_height', 650) 

    st.set_page_config(layout="wide", page_title="Optimizacija Gostiju po Sobama")
    st.markdown("<h5 style='font-size: 24px; color: #0056b3; text-align: center;'>🏨 Optimizacija Rasporeda Gostiju po Sobama</h1>", unsafe_allow_html=True)
    st.markdown("---")

    if 'individual_rooms' not in st.session_state: 
        st.session_state.individual_rooms = []
    if 'global_meal_prices' not in st.session_state: 
        st.session_state.global_meal_prices = {'breakfast': 10.0, 'lunch': 15.0, 'dinner': 20.0}
    
    if not st.session_state.individual_rooms and 'predefined_rooms_added_v3' not in st.session_state: 
        predefined_individual_rooms = [ 
            {'id': 'S-001', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-002', 'name': 'Exec | K1+T2+S1', 'single_beds': 2, 'double_beds': 1, 'sofa_beds': 1, 'price': 200.0, 'priority': 4, 'is_available': True},
            {'id': 'S-003', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-004', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-005', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-101', 'name': 'Junr | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'priority': 3, 'is_available': True},
            {'id': 'S-102', 'name': 'Junr | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'priority': 3, 'is_available': True},
            {'id': 'S-103', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-104', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-105', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-106', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-107', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-108', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-109', 'name': 'King | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 130.0, 'priority': 1, 'is_available': True}, 
            {'id': 'S-110', 'name': 'Exec | K1+T1+S1', 'single_beds': 1, 'double_beds': 1, 'sofa_beds': 1, 'price': 200.0, 'priority': 4, 'is_available': True},
            {'id': 'S-111', 'name': 'Junr | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'priority': 3, 'is_available': True},
            {'id': 'S-201', 'name': 'Junr | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'priority': 3, 'is_available': True},
            {'id': 'S-202', 'name': 'Exec | K1+T2+S1', 'single_beds': 2, 'double_beds': 1, 'sofa_beds': 1, 'price': 200.0, 'priority': 4, 'is_available': True},
            {'id': 'S-203', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-204', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-205', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-206', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-207', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-208', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-209', 'name': 'King | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 130.0, 'priority': 1, 'is_available': True}, 
            {'id': 'S-210', 'name': 'Exec | K1+T1+S1', 'single_beds': 1, 'double_beds': 1, 'sofa_beds': 1, 'price': 200.0, 'priority': 4, 'is_available': True},
            {'id': 'S-211', 'name': 'Junr | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'priority': 3, 'is_available': True},
            {'id': 'S-301', 'name': 'Royl | K1+T2+S1', 'single_beds': 2, 'double_beds': 1, 'sofa_beds': 1, 'price': 240.0, 'priority': 5, 'is_available': True},
            {'id': 'S-302', 'name': 'Royl | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 240.0, 'priority': 5, 'is_available': True},
            {'id': 'S-303', 'name': 'Junr | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'priority': 3, 'is_available': True},
            {'id': 'S-304', 'name': 'Royl | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 240.0, 'priority': 5, 'is_available': True},
            {'id': 'S-305', 'name': 'Royl | K1+T2+S1', 'single_beds': 2, 'double_beds': 1, 'sofa_beds': 1, 'price': 240.0, 'priority': 5, 'is_available': True},
        ]
        st.session_state.individual_rooms.extend(predefined_individual_rooms)
        st.session_state.predefined_rooms_added_v3 = True 
    
    st.sidebar.header("Kontrole i Podešavanja")
    allocation_button = st.sidebar.button("Pokreni Optimizaciju Rasporeda", type="primary", use_container_width=True, key="run_optimization_button")
    st.sidebar.markdown("---")

    with st.sidebar.container():
        st.subheader("Parametri Gostiju")
        total_guests_input = st.number_input("Ukupan broj gostiju za raspored", min_value=0, value=st.session_state.get('last_total_guests', 30), step=1, key="total_guests_main_input")
        
        default_solo_val = st.session_state.get('last_solo_guests_count', 0)
        if default_solo_val > total_guests_input: default_solo_val = total_guests_input if total_guests_input >= 0 else 0
        solo_guests_val = st.number_input(
            "1. Broj solo gostiju (zasebna soba, 1 osoba)",
            min_value=0, value=default_solo_val, step=1, max_value=total_guests_input, 
            key="solo_guests_main_input", help="Gosti koji zahtevaju celu sobu samo za sebe."
        )
        
        remaining_after_solo = total_guests_input - solo_guests_val
        if remaining_after_solo < 0: remaining_after_solo = 0

        default_exclusive_couples_num = st.session_state.get('last_exclusive_couples_count', 0) 
        max_exclusive_couples_allowable = remaining_after_solo // 2
        if default_exclusive_couples_num > max_exclusive_couples_allowable: default_exclusive_couples_num = max_exclusive_couples_allowable
        exclusive_couples_num_input = st.number_input(
            "2. Broj parova (zasebna soba, dele krevet)",
            min_value=0, value=default_exclusive_couples_num, step=1, max_value=max_exclusive_couples_allowable,
            key="exclusive_couples_main_input", help="Parovi koji žele celu sobu za sebe (2 osobe po sobi)."
        )
        exclusive_couples_guests_val = exclusive_couples_num_input * 2

        remaining_after_exclusive_couples = remaining_after_solo - exclusive_couples_guests_val
        if remaining_after_exclusive_couples < 0: remaining_after_exclusive_couples = 0

        default_flexible_pairs_guests = st.session_state.get('last_flexible_pairs_guests_count', 0)
        if default_flexible_pairs_guests > remaining_after_exclusive_couples: default_flexible_pairs_guests = remaining_after_exclusive_couples
        if default_flexible_pairs_guests % 2 != 0: default_flexible_pairs_guests = default_flexible_pairs_guests - 1 if default_flexible_pairs_guests > 0 else 0
        if default_flexible_pairs_guests < 0: default_flexible_pairs_guests = 0
        
        max_flexible_pairs_allowable = remaining_after_exclusive_couples
        if max_flexible_pairs_allowable % 2 != 0 : max_flexible_pairs_allowable = max(0, max_flexible_pairs_allowable -1)

        flexible_pairs_guests_val = st.number_input(
            "3. Broj gostiju u parovima (dele krevet, mogu deliti sobu)",
            min_value=0, value=default_flexible_pairs_guests, step=2, max_value=max_flexible_pairs_allowable,
            help="Gosti koji dolaze kao parovi i dele krevet, ali mogu biti u sobi sa drugima ako kapacitet dozvoljava.",
            key="flexible_pairs_main_input"
        )
        
        individual_guests_calculated_val = total_guests_input - solo_guests_val - exclusive_couples_guests_val - flexible_pairs_guests_val
        if individual_guests_calculated_val < 0: individual_guests_calculated_val = 0 
        
        st.markdown(f"<p style='font-size: 1.0em; color: #555;'>Broj individualnih gostiju (dele sobu, ne krevet): <strong style='color: #0061b3;'>{individual_guests_calculated_val}</strong></p>", unsafe_allow_html=True)

        can_run_allocation_flag = True 
        current_total_categorized_guests = solo_guests_val + exclusive_couples_guests_val + flexible_pairs_guests_val
        if current_total_categorized_guests > total_guests_input :
            st.sidebar.error("Zbir kategorisanih gostiju (1, 2, 3) premašuje ukupan broj gostiju!")
            can_run_allocation_flag = False
        elif individual_guests_calculated_val < 0: 
             st.sidebar.error("Nevalidna kombinacija broja gostiju (rezultira negativnim brojem individualaca).")
             can_run_allocation_flag = False

    st.sidebar.markdown("---")
    with st.sidebar.container():
        st.subheader("Trajanje boravka")
        num_days_val = st.number_input("Broj dana boravka", min_value=1, value=st.session_state.get('last_num_days',1), step=1, key="num_days_main_input")
    st.sidebar.markdown("---")

    st.sidebar.subheader("Izbor obroka za raspored")
    col_bf, col_lu, col_di = st.sidebar.columns(3)
    with col_bf: breakfast_chosen_val = st.checkbox("Doručak", value=st.session_state.get('last_bf', True), key="bf_main_check")
    with col_lu: lunch_chosen_val = st.checkbox("Ručak", value=st.session_state.get('last_lu', False), key="lu_main_check")
    with col_di: dinner_chosen_val = st.checkbox("Večera", value=st.session_state.get('last_di', True), key="di_main_check")
    st.sidebar.markdown("---")

    st.sidebar.subheader("Kriterijumi rasporeda")
    max_price_per_guest_val = st.sidebar.number_input(
        "Ciljna maksimalna ukupna cena po gostu (smeštaj + obroci, €)",
        min_value=0.0, value=st.session_state.get('max_price_per_guest_val_sess', 80.0), step=1.0, format="%.2f", 
        help="Ovo je ciljna cena po gostu (računato na maksimalni kapacitet sobe).",
        key="max_price_main_input"
    )
    st.sidebar.markdown("---")
    new_alloc_table_height = st.sidebar.number_input("Podesi visinu tabele rasporeda (px)", min_value=200, max_value=2000, value=ALLOCATION_TABLE_HEIGHT, step=50, key="alloc_table_height_input")
    if new_alloc_table_height != ALLOCATION_TABLE_HEIGHT:
        st.session_state.allocation_table_height = new_alloc_table_height
        ALLOCATION_TABLE_HEIGHT = new_alloc_table_height 
    st.sidebar.markdown("---")
    if st.sidebar.button("Resetuj sve postavke", key="reset_all_main_button"):
        rooms_backup = st.session_state.get('individual_rooms', []).copy() 
        meals_backup = st.session_state.get('global_meal_prices', {'breakfast': 10.0, 'lunch': 15.0, 'dinner': 20.0}).copy()
        predefined_backup_flag = st.session_state.get('predefined_rooms_added_v3', False)
        keys_to_preserve = {'individual_rooms', 'global_meal_prices', 'predefined_rooms_added_v3', 'allocation_table_height'}
        keys_to_delete = [key for key in st.session_state.keys() if key not in keys_to_preserve]
        for key in keys_to_delete: del st.session_state[key]
        if 'individual_rooms' not in st.session_state : st.session_state.individual_rooms = rooms_backup
        if 'global_meal_prices' not in st.session_state : st.session_state.global_meal_prices = meals_backup
        if predefined_backup_flag and 'predefined_rooms_added_v3' not in st.session_state: st.session_state.predefined_rooms_added_v3 = predefined_backup_flag
        if 'allocation_table_height' not in st.session_state : st.session_state.allocation_table_height = 650 
        st.success("Parametri alokacije su resetovani.")
        st.rerun()

    tab_hotel_management, tab_reports = st.tabs(["⚙️ Upravljanje Hotelom", "📊 Izveštaji i Optimizacija"])

    with tab_hotel_management:
        st.markdown("### ⚙️ Upravljanje Hotelom")
        st.write("Ovde možete konfigurisati pojedinačne sobe i cene obroka.")
        tab_available_rooms, tab_edit_rooms_and_availability, tab_meal_settings = st.tabs([
            "🔢 Pregled Soba", "✏️ Izmeni Detalje Soba", "🍽️ Postavke Cena Obroka"
        ])
        
        with tab_available_rooms:
            st.markdown("#### 🔢 Brza Izmena Dostupnosti Soba")
            if not st.session_state.individual_rooms:
                st.info("Nema definisanih soba.")
            else:
                sorted_rooms = sorted(st.session_state.individual_rooms, key=lambda r: r['id'])
                
                num_columns = 6 
                cols = st.columns(num_columns)

                for i, room_iter in enumerate(sorted_rooms):
                    with cols[i % num_columns]:
                        with st.container(border=True):
                            current_availability = room_iter.get('is_available', True)
                            checkbox_key = f"availability_checkbox_{room_iter['id']}"
                            
                            info_col, cb_col = st.columns([0.65, 0.35]) 

                            with info_col:
                                st.markdown(
                                    f"<div style='font-size: 0.85em; font-weight: bold; padding-top: 6px;'>{room_iter['id']}</div>", 
                                    unsafe_allow_html=True
                                )
                            
                            with cb_col:
                                st.checkbox(
                                    " ", 
                                    value=current_availability,
                                    key=checkbox_key,
                                    on_change=toggle_room_availability_callback,
                                    args=(room_iter['id'], checkbox_key),
                                    help=f"Dostupnost za: {room_iter['id']} ({room_iter['name']})" 
                                )
            
            st.markdown("---") 
            st.markdown("#### Detaljan tabelarni pregled svih soba")
            
            def highlight_unavailable_rows(row):
                color = 'mistyrose' 
                default_style = [''] * len(row) 
                if row['Dostupna'] == "Ne":
                    return [f'background-color: {color}'] * len(row)
                return default_style

            if st.session_state.individual_rooms:
                rooms_df_data_display = []
                for r_display in st.session_state.individual_rooms: 
                    rooms_df_data_display.append({
                        "ID Sobe": r_display['id'], 
                        "Naziv Sobe": r_display['name'], 
                        "TWIN Kreveti": r_display['single_beds'], 
                        "KING Kreveti": r_display['double_beds'], 
                        "SOFA Kreveti": r_display['sofa_beds'], 
                        "Maks. Kapacitet": r_display['single_beds']*1 + r_display['double_beds']*2 + r_display['sofa_beds']*2, 
                        "Cena (€)": f"{r_display['price']:.2f}", 
                        "Prioritet": r_display.get('priority',1), 
                        "Dostupna": "Da" if r_display.get('is_available', True) else "Ne"
                    })
                
                df_rooms = pd.DataFrame(rooms_df_data_display)
                styled_df_rooms = df_rooms.style.apply(highlight_unavailable_rows, axis=1)
                
                # PRIMENJENA IZMENA: Dodat height parametar
                st.dataframe(styled_df_rooms, use_container_width=True, hide_index=True, height=ALLOCATION_TABLE_HEIGHT)

            elif not st.session_state.individual_rooms:
                st.info("Nema definisanih soba za detaljan prikaz.")

        with tab_edit_rooms_and_availability:
            st.markdown("#### ✏️ Izmeni Detalje Soba")
            if not st.session_state.individual_rooms: st.info("Nema soba za izmenu.")
            else:
                for i_room_edit_tab, room_to_edit_tab in enumerate(st.session_state.individual_rooms):
                    availability_status_text = "Dostupna" if room_to_edit_tab.get('is_available', True) else "Nije dostupna"
                    exp_title_tab = f"{room_to_edit_tab['name']} (ID: {room_to_edit_tab['id']}) - Status: {availability_status_text}"
                    
                    with st.expander(exp_title_tab): 
                        form_key_tab = f"form_edit_tab_{room_to_edit_tab['id']}_{i_room_edit_tab}"
                        with st.form(form_key_tab):
                            col_form_edit_1, col_form_edit_2 = st.columns(2)
                            with col_form_edit_1:
                                st.text_input("ID Sobe", value=room_to_edit_tab['id'], disabled=True, key=f"text_id_edit_val_{room_to_edit_tab['id']}_{i_room_edit_tab}")
                                new_name_val_form = st.text_input("Naziv", value=room_to_edit_tab['name'], key=f"text_name_edit_val_{room_to_edit_tab['id']}_{i_room_edit_tab}")                                     
                                new_price_val_form = st.number_input("Cena (€)", value=room_to_edit_tab['price'], min_value=0.0, step=0.01, format="%.2f", key=f"num_p_edit_val_{room_to_edit_tab['id']}_{i_room_edit_tab}")
                                new_priority_val_form = st.number_input("Prioritet", value=room_to_edit_tab.get('priority', 1), min_value=1, step=1, key=f"num_pr_edit_val_{room_to_edit_tab['id']}_{i_room_edit_tab}")
                            with col_form_edit_2:
                                
                                new_single_beds_val_form = st.number_input("Singl krevet", value=room_to_edit_tab['single_beds'], min_value=0, step=1, key=f"num_s_edit_val_{room_to_edit_tab['id']}_{i_room_edit_tab}")
                                new_double_beds_val_form = st.number_input("King size", value=room_to_edit_tab['double_beds'], min_value=0, step=1, key=f"num_d_edit_val_{room_to_edit_tab['id']}_{i_room_edit_tab}")
                                new_sofa_beds_val_form = st.number_input("Sofa", value=room_to_edit_tab['sofa_beds'], min_value=0, step=1, key=f"num_sf_edit_val_{room_to_edit_tab['id']}_{i_room_edit_tab}")
                            
                            st.caption(f"Dostupnost se menja u tabu 'Pregled Soba'. Trenutni status: {availability_status_text}")
                            st.info(f"Globalne cene obroka: D={st.session_state.global_meal_prices['breakfast']:.2f}€, R={st.session_state.global_meal_prices['lunch']:.2f}€, V={st.session_state.global_meal_prices['dinner']:.2f}€.")
                            
                            if st.form_submit_button("Ažuriraj Detalje"): 
                                if (new_single_beds_val_form + new_double_beds_val_form + new_sofa_beds_val_form) == 0: st.error("Soba mora imati barem jedan krevet.")
                                else:
                                    idx_to_update_form = next((k_idx_form for k_idx_form, r_find_form in enumerate(st.session_state.individual_rooms) if r_find_form['id'] == room_to_edit_tab['id']), -1)
                                    if idx_to_update_form != -1:
                                        st.session_state.individual_rooms[idx_to_update_form].update({
                                            'name': new_name_val_form, 
                                            'single_beds': int(new_single_beds_val_form),
                                            'double_beds': int(new_double_beds_val_form), 
                                            'sofa_beds': int(new_sofa_beds_val_form),
                                            'price': float(new_price_val_form), 
                                            'priority': int(new_priority_val_form)
                                        })
                                        st.success(f"Detalji sobe '{new_name_val_form}' ažurirani."); st.rerun() 
                                    else: st.error("Greška: Soba nije pronađena.")
        with tab_meal_settings:
            st.markdown("#### 🍽️ Postavke Cena Obroka (Globalne)")
            with st.form("global_meal_prices_form_main_key"): 
                gmp_s = st.session_state.global_meal_prices
                bf_p_n = st.number_input("Doručak (€)", value=gmp_s.get('breakfast',0.0), min_value=0.0, step=0.1, format="%.2f", key="bf_p_main_form")
                l_p_n = st.number_input("Ručak (€)", value=gmp_s.get('lunch',0.0), min_value=0.0, step=0.1, format="%.2f", key="l_p_main_form")
                d_p_n = st.number_input("Večera (€)", value=gmp_s.get('dinner',0.0), min_value=0.0, step=0.1, format="%.2f", key="d_p_main_form")
                if st.form_submit_button("Sačuvaj cene"): 
                    st.session_state.global_meal_prices = {'breakfast': bf_p_n, 'lunch': l_p_n, 'dinner': d_p_n }
                    st.success("Globalne cene obroka ažurirane."); st.rerun() 

    with tab_reports:
        st.markdown("### 📊 Izveštaji i Optimizacija")
        if allocation_button:
            if not can_run_allocation_flag: st.error("Molimo ispravite unos parametara gostiju u sidebar-u.")
            elif not st.session_state.individual_rooms or not any(r.get('is_available', True) for r in st.session_state.individual_rooms):
                st.error("Nema definisanih ili dostupnih soba za alokaciju.")
            elif total_guests_input == 0:
                st.info("Nema gostiju za raspored (ukupan broj gostiju je 0).")
                keys_to_clear = [k for k in st.session_state if k.startswith('last_') or k == 'max_price_per_guest_val_sess']
                for key_clr in keys_to_clear:
                    if key_clr in st.session_state: del st.session_state[key_clr]
                if 'last_allocation_results' in st.session_state: del st.session_state['last_allocation_results']
                if 'last_avg_prices_by_guest_type' in st.session_state: del st.session_state['last_avg_prices_by_guest_type']
            else:
                st.info("Pokrećem optimizaciju rasporeda...")
                (res_allocation, res_room_income, res_meal_income, 
                res_total_accommodated, res_remaining_guests, res_status_msg, 
                res_avg_price_bed, res_rooms_used, res_rooms_in_budget, 
                res_num_avail_rooms_initially, 
                res_avail_beds_cap, res_hotel_beds, 
                res_avg_price_guest_total, res_avg_price_room, 
                res_phys_rooms, res_room_income_days, res_meal_income_days,
                avg_prices_by_type_result) = perform_allocation(
                    total_guests_input, solo_guests_val, exclusive_couples_guests_val, 
                    flexible_pairs_guests_val, max_price_per_guest_val, 
                    breakfast_chosen_val, lunch_chosen_val, dinner_chosen_val,
                    st.session_state.individual_rooms, st.session_state.global_meal_prices, num_days_val
                )
                st.session_state.update({
                    'last_total_guests': total_guests_input, 'last_solo_guests_count': solo_guests_val,
                    'last_exclusive_couples_count': exclusive_couples_num_input, 
                    'last_flexible_pairs_guests_count': flexible_pairs_guests_val, 
                    'last_num_days': num_days_val, 'last_bf': breakfast_chosen_val, 
                    'last_lu': lunch_chosen_val, 'last_di': dinner_chosen_val,
                    'max_price_per_guest_val_sess': max_price_per_guest_val, 
                    'last_allocation_results': res_allocation, 
                    'last_total_room_income': res_room_income, 'last_total_meal_income': res_meal_income,
                    'last_total_accommodated': res_total_accommodated, 'last_remaining_guests': res_remaining_guests,
                    'last_status_message': res_status_msg, 'last_avg_achieved_price_per_bed': res_avg_price_bed,
                    'last_total_rooms_used_count': res_rooms_used, 'last_num_rooms_within_budget': res_rooms_in_budget,
                    'last_num_available_rooms_initially': res_num_avail_rooms_initially,
                    'last_total_available_beds_capacity': res_avail_beds_cap, 
                    'last_total_hotel_capacity_beds': res_hotel_beds, 
                    'last_avg_price_per_guest_incl_meals': res_avg_price_guest_total,
                    'last_avg_price_per_occupied_room': res_avg_price_room,
                    'last_total_physical_rooms_in_hotel': res_phys_rooms,
                    'last_total_room_income_for_num_days': res_room_income_days,
                    'last_total_meal_income_for_num_days': res_meal_income_days,
                    'last_avg_prices_by_guest_type': avg_prices_by_type_result 
                })
                st.rerun()

        if 'last_allocation_results' in st.session_state and st.session_state.get('last_total_guests', -1) >= 0 : 
            st.markdown("---")
            ls_res_disp = st.session_state 
            
            if ls_res_disp.last_status_message == "no_guests_requested" and ls_res_disp.last_total_guests == 0:
                st.info("Nije bilo zahteva za smeštaj gostiju (ukupan broj gostiju je 0).")
            elif ls_res_disp.last_total_guests >= 0 : 
                if ls_res_disp.last_total_guests > 0: 
                    st.markdown("### Detaljan Izveštaj Rasporeda")
                    if ls_res_disp.last_status_message == "success": st.success(f"Uspešno je smešteno svih {ls_res_disp.last_total_accommodated} od traženih {ls_res_disp.last_total_guests} gostiju!")
                    elif ls_res_disp.last_status_message == "partial_success": st.warning(f"Delimično uspešno: Smešteno je {ls_res_disp.last_total_accommodated} od traženih {ls_res_disp.last_total_guests} gostiju. {ls_res_disp.last_remaining_guests} gostiju nije smešteno.")
                    elif ls_res_disp.last_status_message == "no_rooms_available": st.error("Nijedna soba nije dostupna za alokaciju.")
                    elif ls_res_disp.last_status_message == "no_guests_accommodated": st.error("Nijedan gost nije mogao biti smešten sa trenutnim parametrima i dostupnim sobama.")
                    elif ls_res_disp.last_status_message == "no_rooms_within_budget_and_no_guests" : st.error(f"Nijedna dostupna soba ne zadovoljava budžet ({max_price_per_guest_val:.2f} €/gost) i nijedan gost nije smešten.")
                    elif ls_res_disp.last_status_message == "all_rooms_over_budget": st.warning(f"Svi gosti su smešteni, ali sve korišćene sobe premašuju postavljeni budžet po gostu ({max_price_per_guest_val:.2f} €).")
                    else: st.info(f"Status alokacije: {ls_res_disp.last_status_message}")


                naslov_sum_stil = "background-color: #d5e2ed; color: #004080; padding: 10px; border-radius: 5px; font-weight: bold;"
                st.markdown(f"<div style='{naslov_sum_stil}'><h3 style='margin-bottom: 0;'>Sumarni pregled ključnih metrika:</h3></div>", unsafe_allow_html=True)
                st.write("") 
                
                summary_data_list_disp = [
                    {"Metrika": "Ukupan broj gostiju (po zahtevu)", "Vrednost": ls_res_disp.last_total_guests},
                    {"Metrika": "Ukupan broj raspoloživih soba (na početku)", "Vrednost": ls_res_disp.get('last_num_available_rooms_initially', 'N/A')},
                    {"Metrika": "Broj dana boravka", "Vrednost": ls_res_disp.last_num_days},
                    {"Metrika": "Ukupan kapacitet hotela (svih ležajeva)", "Vrednost": ls_res_disp.last_total_hotel_capacity_beds},
                    {"Metrika": "Ukupno smešteno gostiju", "Vrednost": ls_res_disp.last_total_accommodated},
                    {"Metrika": "Dostupan kapacitet ležajeva (u raspoloživim sobama)", "Vrednost": ls_res_disp.last_total_available_beds_capacity},
                    {"Metrika": "Gosti bez smeštaja", "Vrednost": ls_res_disp.last_remaining_guests},
                    {"Metrika": "Ukupno korišćeno soba", "Vrednost": ls_res_disp.last_total_rooms_used_count},
                    {"Metrika": "Prosečna ostvarena cena po gostu (smeštaj)", "Vrednost": f"{ls_res_disp.last_avg_achieved_price_per_bed:,.2f} €"},
                    {"Metrika": f"Ukupan Prihod (Sobe, za {ls_res_disp.last_num_days} dana)", "Vrednost": f"{ls_res_disp.last_total_room_income_for_num_days:,.2f} €"},
                    {"Metrika": "Prosečna cena po GOSTU (smeštaj + obroci)", "Vrednost": f"{ls_res_disp.last_avg_price_per_guest_incl_meals:,.2f} €"},
                    {"Metrika": f"Ukupan Prihod (Obroci, za {ls_res_disp.last_num_days} dana)", "Vrednost": f"{ls_res_disp.last_total_meal_income_for_num_days:,.2f} €"},
                    {"Metrika": "Prosečna cena po zauzetoj SOBI (smeštaj)", "Vrednost": f"{ls_res_disp.last_avg_price_per_occupied_room:,.2f} €"},
                    {"Metrika": f"Ukupan Prihod (Sobe + Obroci, za {ls_res_disp.last_num_days} dana)", "Vrednost": f"{(ls_res_disp.last_total_room_income_for_num_days + ls_res_disp.last_total_meal_income_for_num_days):,.2f} €"}
                ]
                
                TARGET_METRIC_NAME_STYLE = f"Ukupan Prihod (Sobe + Obroci, za {ls_res_disp.last_num_days} dana)" 
                TARGET_ITEM_BACKGROUND_STYLE = "#D4EDDA" 
                TARGET_ITEM_METRIKA_FONT_COLOR_STYLE = "#1e241f" 
                TARGET_ITEM_METRIKA_FONT_WEIGHT_STYLE = "bold"
                TARGET_ITEM_VREDNOST_FONT_COLOR_STYLE = "#1e241f" 
                TARGET_ITEM_VREDNOST_FONT_STYLE = "font-weight: bold;" 

                TARGET_METRIC_NAME_STYLE_2 = "Prosečna cena po zauzetoj SOBI (smeštaj)" 
                TARGET_ITEM_BACKGROUND_STYLE_2 = "#D4EDDA" 
                TARGET_ITEM_METRIKA_FONT_COLOR_STYLE_2 = "#1e241f"
                TARGET_ITEM_METRIKA_FONT_WEIGHT_STYLE_2 = "bold"
                TARGET_ITEM_VREDNOST_FONT_COLOR_STYLE_2 = "#1e241f"
                TARGET_ITEM_VREDNOST_FONT_STYLE_2 = "font-weight: bold;"
                
                TARGET_METRIC_NAME_STYLE_4 = "Ukupno korišćeno soba" 
                TARGET_ITEM_BACKGROUND_STYLE_4 = "#ffeede" 
                TARGET_ITEM_METRIKA_FONT_COLOR_STYLE_4 = "#403d34" 
                TARGET_ITEM_METRIKA_FONT_WEIGHT_STYLE_4 = "bold"
                TARGET_ITEM_VREDNOST_FONT_COLOR_STYLE_4 = "#403d34" 
                TARGET_ITEM_VREDNOST_FONT_STYLE_4 = "font-weight: bold; font-style: normal;" 
                
                TARGET_METRIC_NAME_STYLE_5 = "Prosečna cena po GOSTU (smeštaj + obroci)" 
                TARGET_ITEM_BACKGROUND_STYLE_5 = "#ffeede" 
                TARGET_ITEM_METRIKA_FONT_COLOR_STYLE_5 = "#403d34" 
                TARGET_ITEM_METRIKA_FONT_WEIGHT_STYLE_5 = "bold"
                TARGET_ITEM_VREDNOST_FONT_COLOR_STYLE_5 = "#403d34" 
                TARGET_ITEM_VREDNOST_FONT_STYLE_5 = "font-weight: bold; font-style: normal;" 

                DEFAULT_ITEM_METRIKA_FONT_COLOR_STYLE = "#282b2e"  
                DEFAULT_ITEM_METRIKA_FONT_WEIGHT_STYLE = "normal" 
                DEFAULT_ITEM_VREDNOST_FONT_COLOR_STYLE = "#282b2e" 
                DEFAULT_ITEM_VREDNOST_FONT_STYLE = "font-style: normal;" 
                DEFAULT_ITEM_BACKGROUND_STYLE = "#fffffb"

                KPI_ITEMS_FONT_SIZE = "0.87em" 
                kpi_container_style = "padding: 7px; margin-bottom: 7px; border-radius: 5px; border: 1px solid #dee2e6;"

                col1, col2 = st.columns(2)

                for i, kpi_item in enumerate(summary_data_list_disp): 
                    metrika = kpi_item["Metrika"]
                    vrednost = str(kpi_item["Vrednost"]) 

                    current_bg = DEFAULT_ITEM_BACKGROUND_STYLE
                    metrika_html_style_str = f"color: {DEFAULT_ITEM_METRIKA_FONT_COLOR_STYLE}; font-weight: {DEFAULT_ITEM_METRIKA_FONT_WEIGHT_STYLE}; font-size: {KPI_ITEMS_FONT_SIZE};"
                    vrednost_html_style_str = f"color: {DEFAULT_ITEM_VREDNOST_FONT_COLOR_STYLE}; {DEFAULT_ITEM_VREDNOST_FONT_STYLE} font-size: {KPI_ITEMS_FONT_SIZE};"

                    if metrika == TARGET_METRIC_NAME_STYLE: 
                        current_bg = TARGET_ITEM_BACKGROUND_STYLE
                        metrika_html_style_str = f"color: {TARGET_ITEM_METRIKA_FONT_COLOR_STYLE}; font-weight: {TARGET_ITEM_METRIKA_FONT_WEIGHT_STYLE}; font-size: {KPI_ITEMS_FONT_SIZE};"
                        vrednost_html_style_str = f"color: {TARGET_ITEM_VREDNOST_FONT_COLOR_STYLE}; {TARGET_ITEM_VREDNOST_FONT_STYLE} font-size: {KPI_ITEMS_FONT_SIZE};"
                    
                    elif metrika == TARGET_METRIC_NAME_STYLE_2: 
                        current_bg = TARGET_ITEM_BACKGROUND_STYLE_2
                        metrika_html_style_str = f"color: {TARGET_ITEM_METRIKA_FONT_COLOR_STYLE_2}; font-weight: {TARGET_ITEM_METRIKA_FONT_WEIGHT_STYLE_2}; font-size: {KPI_ITEMS_FONT_SIZE};"
                        vrednost_html_style_str = f"color: {TARGET_ITEM_VREDNOST_FONT_COLOR_STYLE_2}; {TARGET_ITEM_VREDNOST_FONT_STYLE_2} font-size: {KPI_ITEMS_FONT_SIZE};"
                        
                    elif metrika == TARGET_METRIC_NAME_STYLE_4: 
                        current_bg = TARGET_ITEM_BACKGROUND_STYLE_4
                        metrika_html_style_str = f"color: {TARGET_ITEM_METRIKA_FONT_COLOR_STYLE_4}; font-weight: {TARGET_ITEM_METRIKA_FONT_WEIGHT_STYLE_4}; font-size: {KPI_ITEMS_FONT_SIZE};"
                        vrednost_html_style_str = f"color: {TARGET_ITEM_VREDNOST_FONT_COLOR_STYLE_4}; {TARGET_ITEM_VREDNOST_FONT_STYLE_4} font-size: {KPI_ITEMS_FONT_SIZE};"

                    elif metrika == TARGET_METRIC_NAME_STYLE_5: 
                        current_bg = TARGET_ITEM_BACKGROUND_STYLE_5
                        metrika_html_style_str = f"color: {TARGET_ITEM_METRIKA_FONT_COLOR_STYLE_5}; font-weight: {TARGET_ITEM_METRIKA_FONT_WEIGHT_STYLE_5}; font-size: {KPI_ITEMS_FONT_SIZE};"
                        vrednost_html_style_str = f"color: {TARGET_ITEM_VREDNOST_FONT_COLOR_STYLE_5}; {TARGET_ITEM_VREDNOST_FONT_STYLE_5} font-size: {KPI_ITEMS_FONT_SIZE};"
                    
                    display_metrika_html = metrika.replace("  ", "&nbsp;&nbsp;") 
                    
                    html_content_kpi = f"""
                    <div style="background-color: {current_bg}; {kpi_container_style} display: flex; justify-content: space-between; align-items: center;">
                        <span style="text-align: left; flex-grow: 1; {metrika_html_style_str}">{display_metrika_html}</span>
                        <span style="text-align: right; {vrednost_html_style_str}">{vrednost}</span>
                    </div>
                    """
                    if i % 2 == 0: 
                        col1.markdown(html_content_kpi, unsafe_allow_html=True)
                    else: 
                        col2.markdown(html_content_kpi, unsafe_allow_html=True)

                st.markdown("---") 

                if 'last_avg_prices_by_guest_type' in ls_res_disp:
                    st.markdown("#### Prosečne efektivne cene po tipu gosta (sa obrocima)")
                    avg_prices_data_for_df = []
                    guest_type_display_order = [
                        "Solo Gost (zasebna soba)", "Ekskluzivni Par (po osobi, zasebna soba)",
                        "Fleksibilni Par (po osobi, deli krevet i možda sobu)", "Individualni Gost (deli sobu, ne krevet)"
                    ]
                    for guest_type_key in guest_type_display_order:
                        avg_price_val, guest_count_val = ls_res_disp.last_avg_prices_by_guest_type.get(guest_type_key, (0,0)) 
                        if guest_count_val > 0: 
                            avg_prices_data_for_df.append({
                                "Tip gosta": guest_type_key, "Broj gostiju": guest_count_val, 
                                "Prosečna efektivna cena/gost (€)": f"{avg_price_val:.2f} €"
                            })
                    if avg_prices_data_for_df: 
                        df_avg_prices_display = pd.DataFrame(avg_prices_data_for_df)
                        st.dataframe(df_avg_prices_display, use_container_width=True, hide_index=True)
                    else: st.info("Nema podataka za prikaz prosečnih cena po tipu gosta.")
                    st.markdown("---")

                if ls_res_disp.last_total_guests > 0: 
                    st.markdown("### Raspored Gostiju po Sobama")
                    if ls_res_disp.last_allocation_results: 
                        allocation_display_data_list_render = []
                        for item_alloc_render in ls_res_disp.last_allocation_results:
                            total_room_revenue_per_day_item_render = item_alloc_render['room_income'] + item_alloc_render['meal_income']
                            over_budget_status_item_render = "DA" if item_alloc_render['over_max_budget'] else "NE"
                            allocation_display_data_list_render.append({
                                "ID Sobe": item_alloc_render['room_id'], "Naziv Sobe": item_alloc_render['room_name'],
                                "Aranžman Gostiju": item_alloc_render.get('guest_arrangement', 'N/A'),
                                "Smešteno Gostiju": item_alloc_render['guests_accommodated'], "Prioritet": item_alloc_render['priority'], 
                                "Prihod od Sobe (po danu)": f"{item_alloc_render['room_income']:.2f} €",
                                "Prihod od Obroka (po danu)": f"{item_alloc_render['meal_income']:.2f} €",
                                "Ukupan Prihod po Sobi (po danu)": f"{total_room_revenue_per_day_item_render:.2f} €",
                                f"Ukupan Prihod po Sobi (za {ls_res_disp.last_num_days} dana)": f"{(total_room_revenue_per_day_item_render * ls_res_disp.last_num_days):.2f} €",
                                "Efektivna Cena/Gost (€)": f"{item_alloc_render.get('effective_price_per_guest_actual', 0.0):.2f} €", 
                                "Soba preko budžeta (max. kap.)": over_budget_status_item_render,
                                "Cena po gostu (max. kap. + obroci)": f"{item_alloc_render['total_price_per_guest_for_room']:.2f} €"
                            })
                        df_allocation_to_display_render = pd.DataFrame(allocation_display_data_list_render)
                        desired_column_order_render = [
                            "ID Sobe", "Naziv Sobe", "Aranžman Gostiju", "Smešteno Gostiju", "Prioritet",
                            "Prihod od Sobe (po danu)", "Prihod od Obroka (po danu)", "Ukupan Prihod po Sobi (po danu)",
                            f"Ukupan Prihod po Sobi (za {ls_res_disp.last_num_days} dana)", 
                            "Efektivna Cena/Gost (€)", "Soba preko budžeta (max. kap.)", 
                            "Cena po gostu (max. kap. + obroci)"
                        ]
                        existing_columns_in_order_render = [col for col in desired_column_order_render if col in df_allocation_to_display_render.columns]
                        df_to_display_ordered_render = df_allocation_to_display_render[existing_columns_in_order_render]
                        def style_over_budget_column_alloc(val): return f'background-color: mistyrose' if val == "DA" else ''
                        styled_allocation_df_render = df_to_display_ordered_render.style.map(style_over_budget_column_alloc, subset=["Soba preko budžeta (max. kap.)"])
                        st.dataframe(styled_allocation_df_render, use_container_width=True, hide_index=True, height=ALLOCATION_TABLE_HEIGHT)
                    elif ls_res_disp.last_total_guests > 0 and not ls_res_disp.last_allocation_results : 
                        st.info("Nije bilo moguće generisati raspored sa trenutnim parametrima (nema zauzetih soba).")
            
        elif not allocation_button and 'last_allocation_results' not in st.session_state :
            st.info("Unesite parametre u sidebar-u i kliknite na 'Pokreni Optimizaciju Rasporeda' da biste videli izveštaje.")

if __name__ == "__main__":
    main()