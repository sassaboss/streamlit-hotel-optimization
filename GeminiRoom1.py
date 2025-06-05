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

def get_base_type_from_name(room_name):
    if '|' in room_name:
        return room_name.split('|')[0].strip()
    if not room_name:
        return "Unknown"
    return room_name.split(' ')[0]

# --- GLAVNI DEO ZA SORTIRANJE - PRILAGOĐAVANJE PRIORITETA (MODIFIKOVANO v3.3.2) ---
def get_sort_key(room_item, guest_type_for_sort='individual',
                 num_guests_to_place_now=1,
                 room_type_priorities_map=None,
                 default_type_priority=100, 
                 meal_cost_per_guest_for_all_rooms=0.0
                ):
    if room_type_priorities_map is None:
        room_type_priorities_map = {}

    base_type = room_item.get('base_type', 'Unknown')
    is_royl_room = (base_type == 'Royl')

    priority_royl_penalty = 9999 if is_royl_room else 0

    user_priority_for_sorting = default_type_priority
    if not is_royl_room:
        user_priority_for_sorting = room_type_priorities_map.get(base_type, default_type_priority)

    wasted_slots_in_room_overall = float('inf')
    effective_price_per_guest_this_placement = float('inf')
    suitability_penalty = 0
    actual_guests_placed_from_current_group = 0
    fill_factor = 0.0

    room_price = room_item['price']
    s_beds_init = room_item['single_beds_available_in_room_initially']
    d_beds_init = room_item['double_beds_available_in_room_initially']
    sf_beds_init = room_item['sofa_beds_available_in_room_initially']
    total_room_capacity_persons = room_item['calculated_max_capacity_persons']

    implicit_king_priority_penalty = 2 

    if guest_type_for_sort == 'solo' or guest_type_for_sort == 'exclusive_couple':
        if base_type == 'King':
            if d_beds_init == 1 and s_beds_init == 0 and sf_beds_init == 0:
                implicit_king_priority_penalty = 0
            else:
                implicit_king_priority_penalty = 1

    if guest_type_for_sort == 'solo':
        can_accommodate_solo_flag = False
        if d_beds_init > 0 or sf_beds_init > 0:
            can_accommodate_solo_flag = True
            if base_type == 'Twin' and implicit_king_priority_penalty == 2: 
                 suitability_penalty += 50
        elif s_beds_init > 0:
            can_accommodate_solo_flag = True
            suitability_penalty += (10 if base_type == 'Twin' and implicit_king_priority_penalty == 2 else 5)

        if can_accommodate_solo_flag:
            actual_guests_placed_from_current_group = 1
            effective_price_per_guest_this_placement = room_price + meal_cost_per_guest_for_all_rooms
            wasted_slots_in_room_overall = total_room_capacity_persons - 1
            if total_room_capacity_persons > 0: fill_factor = 1.0 / total_room_capacity_persons
        else:
            suitability_penalty = float('inf')

        return (
            priority_royl_penalty, implicit_king_priority_penalty, suitability_penalty,
            wasted_slots_in_room_overall, effective_price_per_guest_this_placement,
            user_priority_for_sorting, -actual_guests_placed_from_current_group,
            -fill_factor, room_item['room_id']
        )

    elif guest_type_for_sort == 'exclusive_couple':
        can_accommodate_couple_flag = (d_beds_init > 0 or sf_beds_init > 0)
        if can_accommodate_couple_flag:
            actual_guests_placed_from_current_group = 2
            effective_price_per_guest_this_placement = (room_price / 2) + meal_cost_per_guest_for_all_rooms
            wasted_slots_in_room_overall = total_room_capacity_persons - 2
            if total_room_capacity_persons > 0: fill_factor = 2.0 / total_room_capacity_persons
        else:
            suitability_penalty = float('inf')
        return (
            priority_royl_penalty, implicit_king_priority_penalty, suitability_penalty,
            wasted_slots_in_room_overall, effective_price_per_guest_this_placement,
            user_priority_for_sorting, -actual_guests_placed_from_current_group,
            -fill_factor, room_item['room_id']
        )

    elif guest_type_for_sort == 'sharing_group':
        temp_d_beds = d_beds_init; temp_sf_beds = sf_beds_init; temp_s_beds_room = s_beds_init
        guests_placed_as_pairs = 0; pairs_to_try_in_group = num_guests_to_place_now // 2
        for _ in range(pairs_to_try_in_group):
            if temp_d_beds > 0: temp_d_beds -= 1; guests_placed_as_pairs += 2
            elif temp_sf_beds > 0: temp_sf_beds -= 1; guests_placed_as_pairs += 2
            else: break
        remaining_individuals_from_group_to_place = num_guests_to_place_now - guests_placed_as_pairs
        guests_placed_as_individuals_on_single = 0
        if remaining_individuals_from_group_to_place > 0:
            can_place_on_single_beds = min(remaining_individuals_from_group_to_place, temp_s_beds_room)
            guests_placed_as_individuals_on_single = can_place_on_single_beds
        actual_guests_placed_from_current_group = guests_placed_as_pairs + guests_placed_as_individuals_on_single
        if actual_guests_placed_from_current_group > 0:
            effective_price_per_guest_this_placement = (room_price / actual_guests_placed_from_current_group) + meal_cost_per_guest_for_all_rooms
            wasted_slots_in_room_overall = total_room_capacity_persons - actual_guests_placed_from_current_group
            if total_room_capacity_persons > 0: fill_factor = actual_guests_placed_from_current_group / total_room_capacity_persons
            if actual_guests_placed_from_current_group < num_guests_to_place_now:
                suitability_penalty += (num_guests_to_place_now - actual_guests_placed_from_current_group) * 10
        else: suitability_penalty = float('inf')
        return (
            priority_royl_penalty, user_priority_for_sorting, suitability_penalty,
            -actual_guests_placed_from_current_group, effective_price_per_guest_this_placement,
            wasted_slots_in_room_overall, -fill_factor if suitability_penalty != float('inf') else float('inf'),
            room_item['room_id']
        )

    elif guest_type_for_sort == 'individual':
        temp_s_beds_ind = s_beds_init; temp_d_beds_ind = d_beds_init; temp_sf_beds_ind = sf_beds_init
        placed_on_single = min(num_guests_to_place_now, temp_s_beds_ind)
        remaining_to_place_ind = num_guests_to_place_now - placed_on_single
        placed_on_large_alone = 0
        if remaining_to_place_ind > 0 and temp_d_beds_ind > 0:
            can_place_on_d = min(remaining_to_place_ind, temp_d_beds_ind)
            placed_on_large_alone += can_place_on_d; remaining_to_place_ind -= can_place_on_d
        if remaining_to_place_ind > 0 and temp_sf_beds_ind > 0:
            can_place_on_sf = min(remaining_to_place_ind, temp_sf_beds_ind)
            placed_on_large_alone += can_place_on_sf
        actual_guests_placed_from_current_group = placed_on_single + placed_on_large_alone
        if actual_guests_placed_from_current_group > 0:
            effective_price_per_guest_this_placement = (room_price / actual_guests_placed_from_current_group) + meal_cost_per_guest_for_all_rooms
            wasted_slots_in_room_overall = total_room_capacity_persons - actual_guests_placed_from_current_group
            if total_room_capacity_persons > 0: fill_factor = actual_guests_placed_from_current_group / total_room_capacity_persons
            if placed_on_large_alone > 0 and (placed_on_single < (num_guests_to_place_now - placed_on_large_alone)):
                 suitability_penalty += 15
            if actual_guests_placed_from_current_group < num_guests_to_place_now:
                 suitability_penalty += (num_guests_to_place_now - actual_guests_placed_from_current_group) * 15
        else: suitability_penalty = float('inf')
        return (
            priority_royl_penalty, user_priority_for_sorting, suitability_penalty,
            -actual_guests_placed_from_current_group,
            wasted_slots_in_room_overall,
            effective_price_per_guest_this_placement,
            -s_beds_init,
            room_item['room_id']
        )

    if suitability_penalty == float('inf'):
        return (priority_royl_penalty, user_priority_for_sorting, suitability_penalty, float('inf'), float('inf'), float('inf'), float('inf'), room_item['room_id'])
    return (
        priority_royl_penalty, implicit_king_priority_penalty, user_priority_for_sorting, 
        suitability_penalty, wasted_slots_in_room_overall,
        effective_price_per_guest_this_placement, -actual_guests_placed_from_current_group,
        -fill_factor, room_item['room_id']
    )

def perform_allocation(total_guests_overall,
                       solo_guests_count,
                       exclusive_couples_guest_count,
                       female_individuals_count,
                       male_individuals_count,
                       female_bed_sharers_count,
                       male_bed_sharers_count,
                       mf_couples_count,
                       max_price_per_guest, breakfast_chosen, lunch_chosen, dinner_chosen,
                       individual_rooms_data, global_meal_prices_data, num_days,
                       room_type_priorities_map
                       ):

    allocation = []
    default_priority_val_for_sorting = max(room_type_priorities_map.values(), default=99) + 1 if room_type_priorities_map else 100

    remaining_solo_guests = solo_guests_count
    remaining_exclusive_couples_guests = exclusive_couples_guest_count
    remaining_female_sharers_total = female_bed_sharers_count
    remaining_male_sharers_total = male_bed_sharers_count
    remaining_female_individuals_generic = female_individuals_count
    remaining_male_individuals_generic = male_individuals_count
    remaining_mf_pairs = mf_couples_count

    meal_cost_per_guest = 0.0
    if breakfast_chosen: meal_cost_per_guest += global_meal_prices_data['breakfast']
    if lunch_chosen: meal_cost_per_guest += global_meal_prices_data['lunch']
    if dinner_chosen: meal_cost_per_guest += global_meal_prices_data['dinner']

    current_available_rooms_for_allocation = [
        room for room in individual_rooms_data if room.get('is_available', True)
    ]

    num_available_rooms_total_initially = len(current_available_rooms_for_allocation)
    total_available_beds_capacity_overall = sum(
        room['single_beds'] * 1 + room['double_beds'] * 2 + room['sofa_beds'] * 2
        for room in current_available_rooms_for_allocation
    )
    
    avg_prices_by_guest_type_with_count_report = {
        "Solo Gost (zasebna soba)": (0, 0),
        "Ekskluzivni Par (po osobi, zasebna soba)": (0, 0),
        "MŽ Par (po osobi, deli sobu sa MŽ)": (0,0),
        "Žena (deli veliki krevet sa Ž)": (0,0),
        "Muškarac (deli veliki krevet sa M)": (0,0),
        "Ženski Individualac (deli žensku sobu)": (0,0),
        "Muški Individualac (deli mušku sobu)": (0,0)
    }

    if not current_available_rooms_for_allocation:
        return [], 0.0, 0.0, 0, total_guests_overall, "no_rooms_available", 0.0, 0, 0, \
               num_available_rooms_total_initially, total_available_beds_capacity_overall, \
               0, 0, 0, 0.0, 0.0, avg_prices_by_guest_type_with_count_report, 0

    processed_rooms_for_allocation_logic = []
    num_rooms_within_budget_overall = 0
    for r_data_orig in current_available_rooms_for_allocation:
        temp_room_data = r_data_orig.copy()
        if 'base_type' not in temp_room_data or not temp_room_data['base_type']:
            temp_room_data['base_type'] = get_base_type_from_name(temp_room_data['name'])
        max_room_cap_persons = temp_room_data['single_beds'] * 1 + temp_room_data['double_beds'] * 2 + temp_room_data['sofa_beds'] * 2
        temp_room_data['calculated_max_capacity_persons'] = max_room_cap_persons
        temp_room_data['single_beds_available_in_room_initially'] = temp_room_data['single_beds']
        temp_room_data['double_beds_available_in_room_initially'] = temp_room_data['double_beds']
        temp_room_data['sofa_beds_available_in_room_initially'] = temp_room_data['sofa_beds']
        price_per_bed_room_only_max_cap = temp_room_data['price'] / max_room_cap_persons if max_room_cap_persons > 0 else float('inf')
        temp_room_data['price_per_bed_with_meals_max_cap'] = price_per_bed_room_only_max_cap + meal_cost_per_guest
        temp_room_data['over_max_budget'] = temp_room_data['price_per_bed_with_meals_max_cap'] > max_price_per_guest
        if not temp_room_data['over_max_budget']: num_rooms_within_budget_overall += 1
        temp_room_data['has_double_or_sofa_bed'] = (temp_room_data['double_beds'] > 0 or temp_room_data['sofa_beds'] > 0)
        processed_rooms_for_allocation_logic.append(temp_room_data)

    bed_slots_for_allocation = []
    for room_data_proc in processed_rooms_for_allocation_logic:
        bed_slots_for_allocation.append({
            'room_id': room_data_proc['id'], 'room_name': room_data_proc['name'],
            'base_type': room_data_proc['base_type'], 'price': room_data_proc['price'],
            'single_beds_available': room_data_proc['single_beds'],
            'double_beds_available': room_data_proc['double_beds'],
            'sofa_beds_available': room_data_proc['sofa_beds'],
            'single_beds_available_in_room_initially': room_data_proc['single_beds_available_in_room_initially'],
            'double_beds_available_in_room_initially': room_data_proc['double_beds_available_in_room_initially'],
            'sofa_beds_available_in_room_initially': room_data_proc['sofa_beds_available_in_room_initially'],
            'calculated_max_capacity_persons': room_data_proc['calculated_max_capacity_persons'],
            'price_per_bed_with_meals_max_cap': room_data_proc['price_per_bed_with_meals_max_cap'],
            'over_max_budget': room_data_proc['over_max_budget'],
            'has_double_or_sofa_bed': room_data_proc['has_double_or_sofa_bed'],
            'accommodated_guests': 0, 'room_income_this_instance': 0.0,
            'meal_income_this_instance': 0.0, 'is_taken_by_solo_or_exclusive_couple': False,
            'guest_arrangement_details': [], 'gender_type': None,
            'guests_data': [], 'wasted_slots_on_beds': 0
        })

    # FAZA 1: Solo gosti
    if remaining_solo_guests > 0:
        bed_slots_for_allocation.sort(key=lambda x: get_sort_key(x, 'solo', 1, room_type_priorities_map, default_priority_val_for_sorting, meal_cost_per_guest))
        for room_instance in bed_slots_for_allocation:
            if remaining_solo_guests <= 0: break
            if room_instance['accommodated_guests'] > 0: continue
            can_place_solo = False; bed_type_used = ""
            if room_instance['double_beds_available'] > 0 :
                room_instance['double_beds_available'] -=1; bed_type_used = "bračni"; can_place_solo = True; room_instance['wasted_slots_on_beds'] += 1
            elif room_instance['sofa_beds_available'] > 0 :
                room_instance['sofa_beds_available'] -= 1; bed_type_used = "sofa"; can_place_solo = True; room_instance['wasted_slots_on_beds'] += 1
            elif room_instance['single_beds_available'] > 0 :
                room_instance['single_beds_available'] -= 1; bed_type_used = "singl"; can_place_solo = True
            if can_place_solo:
                room_instance['accommodated_guests'] = 1; room_instance['room_income_this_instance'] = room_instance['price']
                room_instance['meal_income_this_instance'] = 1 * meal_cost_per_guest
                room_instance['guest_arrangement_details'].append(f"1 Solo gost (cela soba, {bed_type_used} krevet)")
                price_for_this_solo = room_instance['price'] + meal_cost_per_guest
                room_instance['guests_data'].append({'type': 'solo', 'count': 1, 'price_per_guest': price_for_this_solo})
                remaining_solo_guests -= 1; room_instance['is_taken_by_solo_or_exclusive_couple'] = True
                room_instance['gender_type'] = 'solo_exclusive'
                room_instance['single_beds_available'] = 0; room_instance['double_beds_available'] = 0; room_instance['sofa_beds_available'] = 0

    # FAZA 2: Ekskluzivni parovi
    while remaining_exclusive_couples_guests >= 2:
        bed_slots_for_allocation.sort(key=lambda x: get_sort_key(x, 'exclusive_couple', 2, room_type_priorities_map, default_priority_val_for_sorting, meal_cost_per_guest))
        placed_a_couple_in_this_iteration = False
        for room_instance in bed_slots_for_allocation:
            if remaining_exclusive_couples_guests < 2: break
            if room_instance['is_taken_by_solo_or_exclusive_couple'] or room_instance['accommodated_guests'] > 0: continue
            bed_type_used_for_couple = None
            if room_instance['double_beds_available'] >= 1:
                room_instance['double_beds_available'] -= 1; bed_type_used_for_couple = "bračni"
            elif room_instance['sofa_beds_available'] >= 1:
                room_instance['sofa_beds_available'] -= 1; bed_type_used_for_couple = "sofa"
            if bed_type_used_for_couple:
                room_instance['accommodated_guests'] = 2; room_instance['room_income_this_instance'] = room_instance['price']
                room_instance['meal_income_this_instance'] = 2 * meal_cost_per_guest
                room_instance['guest_arrangement_details'].append(f"Ekskl. Par x1 (zasebna soba, {bed_type_used_for_couple})")
                price_per_person_for_couple = (room_instance['price'] / 2) + meal_cost_per_guest
                room_instance['guests_data'].append({'type': 'exclusive_couple', 'count': 2, 'price_per_guest': price_per_person_for_couple})
                remaining_exclusive_couples_guests -= 2; room_instance['is_taken_by_solo_or_exclusive_couple'] = True
                room_instance['gender_type'] = 'solo_exclusive'
                room_instance['single_beds_available'] = 0; room_instance['double_beds_available'] = 0; room_instance['sofa_beds_available'] = 0
                placed_a_couple_in_this_iteration = True; break
        if not placed_a_couple_in_this_iteration: break

    # FAZA 3: MŽ Parovi
    while remaining_mf_pairs > 0:
        bed_slots_for_allocation.sort(key=lambda x: get_sort_key(x, 'sharing_group', remaining_mf_pairs * 2, room_type_priorities_map, default_priority_val_for_sorting, meal_cost_per_guest))
        placed_mf_pair_in_iteration = False
        for room_instance in bed_slots_for_allocation:
            if remaining_mf_pairs <= 0: break
            if room_instance['is_taken_by_solo_or_exclusive_couple']: continue
            if room_instance['gender_type'] not in [None, 'mixed_mf_couples_only']: continue
            
            actual_d_beds_to_use = room_instance['double_beds_available']
            actual_sf_beds_to_use = room_instance['sofa_beds_available']
            
            pairs_can_fit_mf = actual_d_beds_to_use + actual_sf_beds_to_use
            num_mf_pairs_to_place_in_this_room = min(remaining_mf_pairs, pairs_can_fit_mf)

            if num_mf_pairs_to_place_in_this_room > 0:
                temp_arrangement_details_mf = []
                guests_actually_placed_this_round_mf = 0
                temp_d_beds_taken = 0; temp_sf_beds_taken = 0;
                for _ in range(num_mf_pairs_to_place_in_this_room):
                    if room_instance['double_beds_available'] - temp_d_beds_taken > 0:
                        temp_d_beds_taken += 1; temp_arrangement_details_mf.append("MŽ Par x1 (bračni)")
                    elif room_instance['sofa_beds_available'] - temp_sf_beds_taken > 0:
                        temp_sf_beds_taken += 1; temp_arrangement_details_mf.append("MŽ Par x1 (sofa)")
                    else: break 
                    remaining_mf_pairs -= 1; room_instance['accommodated_guests'] += 2
                    guests_actually_placed_this_round_mf += 2
                
                room_instance['double_beds_available'] -= temp_d_beds_taken
                room_instance['sofa_beds_available'] -= temp_sf_beds_taken
                
                if guests_actually_placed_this_round_mf > 0:
                    if room_instance['room_income_this_instance'] == 0: room_instance['room_income_this_instance'] = room_instance['price']
                    room_instance['meal_income_this_instance'] += guests_actually_placed_this_round_mf * meal_cost_per_guest
                    room_instance['gender_type'] = 'mixed_mf_couples_only'; room_instance['guest_arrangement_details'].extend(temp_arrangement_details_mf)
                    price_per_person_mf = (room_instance['price'] / room_instance['accommodated_guests'] if room_instance['accommodated_guests'] > 0 else 0) + meal_cost_per_guest
                    for _ in range(guests_actually_placed_this_round_mf // 2):
                        room_instance['guests_data'].append({'type': 'mf_couple_shared_room', 'count': 2, 'price_per_guest': price_per_person_mf})
                    if room_instance['gender_type'] == 'mixed_mf_couples_only': room_instance['single_beds_available'] = 0
                    placed_mf_pair_in_iteration = True; break
        if not placed_mf_pair_in_iteration: break

    # FAZA 4: FF Šereri
    while remaining_female_sharers_total > 0:
        bed_slots_for_allocation.sort(key=lambda x: get_sort_key(x, 'sharing_group', remaining_female_sharers_total, room_type_priorities_map, default_priority_val_for_sorting, meal_cost_per_guest))
        placed_ff_group_in_iteration = False
        for room_instance in bed_slots_for_allocation:
            if remaining_female_sharers_total <= 0: break
            if room_instance['is_taken_by_solo_or_exclusive_couple'] or room_instance['gender_type'] == 'mixed_mf_couples_only': continue
            if room_instance['gender_type'] not in [None, 'female']: continue

            s_beds_room_ff_alloc = room_instance['single_beds_available']
            d_beds_room_ff_alloc = room_instance['double_beds_available']
            sf_beds_room_ff_alloc = room_instance['sofa_beds_available']
            
            guests_placed_as_pairs_ff = 0; temp_arrangement_ff_pairs = []
            temp_d_beds_taken_ff = 0; temp_sf_beds_taken_ff = 0; temp_s_beds_taken_ff = 0;
            
            pairs_to_try_ff = min(remaining_female_sharers_total // 2, d_beds_room_ff_alloc + sf_beds_room_ff_alloc)
            for _ in range(pairs_to_try_ff):
                if d_beds_room_ff_alloc - temp_d_beds_taken_ff > 0:
                    temp_d_beds_taken_ff +=1; temp_arrangement_ff_pairs.append("2 Žene (dele bračni krevet)"); guests_placed_as_pairs_ff += 2
                elif sf_beds_room_ff_alloc - temp_sf_beds_taken_ff > 0:
                    temp_sf_beds_taken_ff +=1; temp_arrangement_ff_pairs.append("2 Žene (dele sofa krevet)"); guests_placed_as_pairs_ff += 2
                else: break
            
            remaining_individuals_in_group_ff = remaining_female_sharers_total - guests_placed_as_pairs_ff
            guests_placed_as_individuals_ff = 0; temp_arrangement_ff_individuals = []
            if remaining_individuals_in_group_ff > 0:
                can_place_on_single_ff = min(remaining_individuals_in_group_ff, s_beds_room_ff_alloc)
                for _ in range(can_place_on_single_ff):
                    temp_s_beds_taken_ff +=1; temp_arrangement_ff_individuals.append("Žena Indiv. (iz grupe, singl)")
                    guests_placed_as_individuals_ff += 1
            
            total_guests_placed_this_room_ff = guests_placed_as_pairs_ff + guests_placed_as_individuals_ff

            if total_guests_placed_this_room_ff > 0:
                room_instance['single_beds_available'] -= temp_s_beds_taken_ff
                room_instance['double_beds_available'] -= temp_d_beds_taken_ff
                room_instance['sofa_beds_available'] -= temp_sf_beds_taken_ff
                
                room_instance['accommodated_guests'] += total_guests_placed_this_room_ff
                if room_instance['room_income_this_instance'] == 0: room_instance['room_income_this_instance'] = room_instance['price']
                room_instance['meal_income_this_instance'] += total_guests_placed_this_room_ff * meal_cost_per_guest
                room_instance['gender_type'] = 'female'
                room_instance['guest_arrangement_details'].extend(temp_arrangement_ff_pairs)
                room_instance['guest_arrangement_details'].extend(temp_arrangement_ff_individuals)
                price_per_person_ff_actual = (room_instance['price'] / room_instance['accommodated_guests']) + meal_cost_per_guest
                
                for _ in range(guests_placed_as_pairs_ff // 2):
                     room_instance['guests_data'].append({'type': 'ff_bed_sharer', 'count': 2, 'price_per_guest': price_per_person_ff_actual})
                if guests_placed_as_individuals_ff > 0: 
                     room_instance['guests_data'].append({'type': 'female_individual', 'count': guests_placed_as_individuals_ff, 'price_per_guest': price_per_person_ff_actual, 'note': 'iz FF grupe'})

                remaining_female_sharers_total -= total_guests_placed_this_room_ff
                placed_ff_group_in_iteration = True; break
        if not placed_ff_group_in_iteration: break

    # FAZA 5: MM Šereri
    while remaining_male_sharers_total > 0:
        bed_slots_for_allocation.sort(key=lambda x: get_sort_key(x, 'sharing_group', remaining_male_sharers_total, room_type_priorities_map, default_priority_val_for_sorting, meal_cost_per_guest))
        placed_mm_group_in_iteration = False
        for room_instance in bed_slots_for_allocation:
            if remaining_male_sharers_total <= 0: break
            if room_instance['is_taken_by_solo_or_exclusive_couple'] or room_instance['gender_type'] == 'mixed_mf_couples_only': continue
            if room_instance['gender_type'] not in [None, 'male']: continue

            s_beds_room_mm_alloc = room_instance['single_beds_available']
            d_beds_room_mm_alloc = room_instance['double_beds_available']
            sf_beds_room_mm_alloc = room_instance['sofa_beds_available']
            guests_placed_as_pairs_mm = 0; temp_arrangement_mm_pairs = []
            temp_d_beds_taken_mm = 0; temp_sf_beds_taken_mm = 0; temp_s_beds_taken_mm = 0;
            
            pairs_to_try_mm = min(remaining_male_sharers_total // 2, d_beds_room_mm_alloc + sf_beds_room_mm_alloc)
            for _ in range(pairs_to_try_mm):
                if d_beds_room_mm_alloc - temp_d_beds_taken_mm > 0:
                    temp_d_beds_taken_mm += 1; temp_arrangement_mm_pairs.append("2 Muškarca (dele bračni krevet)"); guests_placed_as_pairs_mm += 2
                elif sf_beds_room_mm_alloc - temp_sf_beds_taken_mm > 0:
                    temp_sf_beds_taken_mm += 1; temp_arrangement_mm_pairs.append("2 Muškarca (dele sofa krevet)"); guests_placed_as_pairs_mm += 2
                else: break
            
            remaining_individuals_in_group_mm = remaining_male_sharers_total - guests_placed_as_pairs_mm
            guests_placed_as_individuals_mm = 0; temp_arrangement_mm_individuals = []
            if remaining_individuals_in_group_mm > 0:
                can_place_on_single_mm = min(remaining_individuals_in_group_mm, s_beds_room_mm_alloc)
                for _ in range(can_place_on_single_mm):
                    temp_s_beds_taken_mm +=1; temp_arrangement_mm_individuals.append("Muškarac Indiv. (iz grupe, singl)")
                    guests_placed_as_individuals_mm += 1
            
            total_guests_placed_this_room_mm = guests_placed_as_pairs_mm + guests_placed_as_individuals_mm

            if total_guests_placed_this_room_mm > 0:
                room_instance['single_beds_available'] -= temp_s_beds_taken_mm
                room_instance['double_beds_available'] -= temp_d_beds_taken_mm
                room_instance['sofa_beds_available'] -= temp_sf_beds_taken_mm
                
                room_instance['accommodated_guests'] += total_guests_placed_this_room_mm
                if room_instance['room_income_this_instance'] == 0: room_instance['room_income_this_instance'] = room_instance['price']
                room_instance['meal_income_this_instance'] += total_guests_placed_this_room_mm * meal_cost_per_guest
                room_instance['gender_type'] = 'male'
                room_instance['guest_arrangement_details'].extend(temp_arrangement_mm_pairs)
                room_instance['guest_arrangement_details'].extend(temp_arrangement_mm_individuals)
                price_per_person_mm_actual = (room_instance['price'] / room_instance['accommodated_guests']) + meal_cost_per_guest
                
                for _ in range(guests_placed_as_pairs_mm // 2):
                     room_instance['guests_data'].append({'type': 'mm_bed_sharer', 'count': 2, 'price_per_guest': price_per_person_mm_actual})
                if guests_placed_as_individuals_mm > 0: 
                     room_instance['guests_data'].append({'type': 'male_individual', 'count': guests_placed_as_individuals_mm, 'price_per_guest': price_per_person_mm_actual, 'note': 'iz MM grupe'})

                remaining_male_sharers_total -= total_guests_placed_this_room_mm
                placed_mm_group_in_iteration = True; break
        if not placed_mm_group_in_iteration: break
        
    if remaining_female_sharers_total > 0:
        remaining_female_individuals_generic += remaining_female_sharers_total
    if remaining_male_sharers_total > 0:
        remaining_male_individuals_generic += remaining_male_sharers_total

    # FAZA 6: Generički Ženski Individualci
    while remaining_female_individuals_generic > 0:
        bed_slots_for_allocation.sort(key=lambda x: get_sort_key(x, 'individual', remaining_female_individuals_generic, room_type_priorities_map, default_priority_val_for_sorting, meal_cost_per_guest))
        placed_f_individual_in_iteration = False
        for room_instance in bed_slots_for_allocation:
            if remaining_female_individuals_generic <= 0: break
            if room_instance['is_taken_by_solo_or_exclusive_couple'] or room_instance['gender_type'] == 'mixed_mf_couples_only': continue
            if room_instance['gender_type'] not in [None, 'female']: continue

            guests_placed_this_room_fi = 0; temp_arrangement_fi = []
            temp_s_beds_taken_fi = 0; temp_d_beds_taken_fi = 0; temp_sf_beds_taken_fi = 0;
            
            # Prvo pokušaj smestiti SVE preostale individualce (ili koliko može) na single krevete
            num_to_try_on_single = min(remaining_female_individuals_generic, room_instance['single_beds_available'])
            for _ in range(num_to_try_on_single):
                temp_s_beds_taken_fi += 1; guests_placed_this_room_fi +=1; temp_arrangement_fi.append("Žena Indiv. x1 (singl)")
            
            # Zatim na double, ako je još ostalo gostiju i kreveta
            remaining_after_single_fi = remaining_female_individuals_generic - guests_placed_this_room_fi
            if remaining_after_single_fi > 0 and room_instance['double_beds_available'] - temp_d_beds_taken_fi > 0: # Provera da li je krevet već uzet
                num_to_try_on_double = min(remaining_after_single_fi, room_instance['double_beds_available'] - temp_d_beds_taken_fi)
                for _ in range(num_to_try_on_double):
                    temp_d_beds_taken_fi += 1; guests_placed_this_room_fi +=1; temp_arrangement_fi.append("Žena Indiv. x1 (bračni)"); room_instance['wasted_slots_on_beds'] += 1
            
            # Zatim na sofe
            remaining_after_double_fi = remaining_female_individuals_generic - guests_placed_this_room_fi
            if remaining_after_double_fi > 0 and room_instance['sofa_beds_available'] - temp_sf_beds_taken_fi > 0:
                num_to_try_on_sofa = min(remaining_after_double_fi, room_instance['sofa_beds_available'] - temp_sf_beds_taken_fi)
                for _ in range(num_to_try_on_sofa):
                    temp_sf_beds_taken_fi += 1; guests_placed_this_room_fi +=1; temp_arrangement_fi.append("Žena Indiv. x1 (sofa)"); room_instance['wasted_slots_on_beds'] += 1
            
            if guests_placed_this_room_fi > 0:
                room_instance['single_beds_available'] -= temp_s_beds_taken_fi
                room_instance['double_beds_available'] -= temp_d_beds_taken_fi
                room_instance['sofa_beds_available'] -= temp_sf_beds_taken_fi
                room_instance['accommodated_guests'] += guests_placed_this_room_fi
                remaining_female_individuals_generic -= guests_placed_this_room_fi
                if room_instance['room_income_this_instance'] == 0: room_instance['room_income_this_instance'] = room_instance['price']
                room_instance['meal_income_this_instance'] += guests_placed_this_room_fi * meal_cost_per_guest
                room_instance['guest_arrangement_details'].extend(temp_arrangement_fi)
                price_per_person_fi_actual = (room_instance['price'] / room_instance['accommodated_guests'] if room_instance['accommodated_guests'] > 0 else 0) + meal_cost_per_guest
                for _ in range(guests_placed_this_room_fi):
                    room_instance['guests_data'].append({'type': 'female_individual', 'count': 1, 'price_per_guest': price_per_person_fi_actual})
                room_instance['gender_type'] = 'female'; placed_f_individual_in_iteration = True; break 
        if not placed_f_individual_in_iteration: break

    # FAZA 7: Generički Muški Individualci
    while remaining_male_individuals_generic > 0:
        bed_slots_for_allocation.sort(key=lambda x: get_sort_key(x, 'individual', remaining_male_individuals_generic, room_type_priorities_map, default_priority_val_for_sorting, meal_cost_per_guest))
        placed_m_individual_in_iteration = False
        for room_instance in bed_slots_for_allocation:
            if remaining_male_individuals_generic <= 0: break
            if room_instance['is_taken_by_solo_or_exclusive_couple'] or room_instance['gender_type'] == 'mixed_mf_couples_only': continue
            if room_instance['gender_type'] not in [None, 'male']: continue

            guests_placed_this_room_mi = 0; temp_arrangement_mi = []
            temp_s_beds_taken_mi = 0; temp_d_beds_taken_mi = 0; temp_sf_beds_taken_mi = 0;

            num_to_try_on_single_mi = min(remaining_male_individuals_generic, room_instance['single_beds_available'])
            for _ in range(num_to_try_on_single_mi):
                temp_s_beds_taken_mi +=1; guests_placed_this_room_mi +=1; temp_arrangement_mi.append("Muškarac Indiv. x1 (singl)")
            
            remaining_after_single_mi = remaining_male_individuals_generic - guests_placed_this_room_mi
            if remaining_after_single_mi > 0 and room_instance['double_beds_available'] - temp_d_beds_taken_mi > 0:
                num_to_try_on_double_mi = min(remaining_after_single_mi, room_instance['double_beds_available'] - temp_d_beds_taken_mi)
                for _ in range(num_to_try_on_double_mi):
                    temp_d_beds_taken_mi +=1; guests_placed_this_room_mi +=1; temp_arrangement_mi.append("Muškarac Indiv. x1 (bračni)"); room_instance['wasted_slots_on_beds'] += 1
            
            remaining_after_double_mi = remaining_male_individuals_generic - guests_placed_this_room_mi
            if remaining_after_double_mi > 0 and room_instance['sofa_beds_available'] - temp_sf_beds_taken_mi > 0:
                num_to_try_on_sofa_mi = min(remaining_after_double_mi, room_instance['sofa_beds_available'] - temp_sf_beds_taken_mi)
                for _ in range(num_to_try_on_sofa_mi):
                    temp_sf_beds_taken_mi +=1; guests_placed_this_room_mi +=1; temp_arrangement_mi.append("Muškarac Indiv. x1 (sofa)"); room_instance['wasted_slots_on_beds'] += 1
            
            if guests_placed_this_room_mi > 0:
                room_instance['single_beds_available'] -= temp_s_beds_taken_mi
                room_instance['double_beds_available'] -= temp_d_beds_taken_mi
                room_instance['sofa_beds_available'] -= temp_sf_beds_taken_mi
                room_instance['accommodated_guests'] += guests_placed_this_room_mi
                remaining_male_individuals_generic -= guests_placed_this_room_mi
                if room_instance['room_income_this_instance'] == 0: room_instance['room_income_this_instance'] = room_instance['price']
                room_instance['meal_income_this_instance'] += guests_placed_this_room_mi * meal_cost_per_guest
                room_instance['guest_arrangement_details'].extend(temp_arrangement_mi)
                price_per_person_mi_actual = (room_instance['price'] / room_instance['accommodated_guests'] if room_instance['accommodated_guests'] > 0 else 0) + meal_cost_per_guest
                for _ in range(guests_placed_this_room_mi):
                    room_instance['guests_data'].append({'type': 'male_individual', 'count': 1, 'price_per_guest': price_per_person_mi_actual})
                room_instance['gender_type'] = 'male'; placed_m_individual_in_iteration = True; break
        if not placed_m_individual_in_iteration: break

    # Agregacija i povratne vrednosti
    aggregated_allocation_final = []
    solo_prices_agg, excl_pair_prices_agg, mf_couple_shared_prices_agg = [], [], []
    ff_sharer_prices_agg, mm_sharer_prices_agg = [], []
    f_ind_prices_agg, m_ind_prices_agg = [], []

    for room_instance_final_agg in bed_slots_for_allocation:
        if room_instance_final_agg['accommodated_guests'] > 0:
            arrangement_counts = {}
            for detail_item in room_instance_final_agg['guest_arrangement_details']:
                arrangement_counts[detail_item] = arrangement_counts.get(detail_item, 0) + 1
            
            unique_details_agg_list = []
            for detail_key, count_val in arrangement_counts.items():
                if count_val == 1: unique_details_agg_list.append(detail_key)
                else: 
                    parts = detail_key.split(' x1 ')
                    if len(parts) == 2: unique_details_agg_list.append(f"{parts[0]} x{count_val} {parts[1]}")
                    else: unique_details_agg_list.append(f"{detail_key} (x{count_val})")
            arrangement_desc_str_agg = ", ".join(unique_details_agg_list) if unique_details_agg_list else "Nije definisano"

            effective_price_per_guest_actual_in_room_agg = 0.0
            if room_instance_final_agg['accommodated_guests'] > 0 :
                effective_price_per_guest_actual_in_room_agg = (room_instance_final_agg['room_income_this_instance'] + room_instance_final_agg['meal_income_this_instance']) / room_instance_final_agg['accommodated_guests']

            for guest_data_item_upd in room_instance_final_agg['guests_data']:
                guest_data_item_upd['price_per_guest'] = effective_price_per_guest_actual_in_room_agg
                price_to_add_agg = guest_data_item_upd['price_per_guest']
                if guest_data_item_upd['type'] == 'solo': solo_prices_agg.append(price_to_add_agg)
                elif guest_data_item_upd['type'] == 'exclusive_couple': excl_pair_prices_agg.extend([price_to_add_agg] * guest_data_item_upd['count'])
                elif guest_data_item_upd['type'] == 'mf_couple_shared_room': mf_couple_shared_prices_agg.extend([price_to_add_agg] * guest_data_item_upd['count'])
                elif guest_data_item_upd['type'] == 'ff_bed_sharer': ff_sharer_prices_agg.extend([price_to_add_agg] * guest_data_item_upd['count'])
                elif guest_data_item_upd['type'] == 'mm_bed_sharer': mm_sharer_prices_agg.extend([price_to_add_agg] * guest_data_item_upd['count'])
                elif guest_data_item_upd['type'] == 'female_individual': f_ind_prices_agg.extend([price_to_add_agg] * guest_data_item_upd['count'])
                elif guest_data_item_upd['type'] == 'male_individual': m_ind_prices_agg.extend([price_to_add_agg] * guest_data_item_upd['count'])

            aggregated_allocation_final.append({
                'room_id': room_instance_final_agg['room_id'], 'room_name': room_instance_final_agg['room_name'],
                'base_type': room_instance_final_agg['base_type'],
                'guests_accommodated': room_instance_final_agg['accommodated_guests'],
                'room_income': room_instance_final_agg['room_income_this_instance'], 
                'meal_income': room_instance_final_agg['meal_income_this_instance'],
                'single_beds_remaining': room_instance_final_agg['single_beds_available'],
                'double_beds_remaining': room_instance_final_agg['double_beds_available'],
                'sofa_beds_remaining': room_instance_final_agg['sofa_beds_available'],
                'room_capacity': room_instance_final_agg['calculated_max_capacity_persons'],
                'total_price_per_guest_for_room_max_cap': room_instance_final_agg['price_per_bed_with_meals_max_cap'],
                'effective_price_per_guest_actual': effective_price_per_guest_actual_in_room_agg,
                'over_max_budget': room_instance_final_agg['over_max_budget'],
                'guest_arrangement': arrangement_desc_str_agg,
                'gender_type_final': room_instance_final_agg['gender_type'],
                'wasted_slots_on_beds_final': room_instance_final_agg['wasted_slots_on_beds']
            })
    
    allocation = sorted(aggregated_allocation_final, key=lambda x: (room_type_priorities_map.get(x['base_type'], default_priority_val_for_sorting), x['room_id']))

    avg_prices_by_guest_type_with_count_report.update({
        "Solo Gost (zasebna soba)": (sum(solo_prices_agg) / len(solo_prices_agg) if solo_prices_agg else 0, len(solo_prices_agg)),
        "Ekskluzivni Par (po osobi, zasebna soba)": (sum(excl_pair_prices_agg) / len(excl_pair_prices_agg) if excl_pair_prices_agg else 0, len(excl_pair_prices_agg)),
        "MŽ Par (po osobi, deli sobu sa MŽ)": (sum(mf_couple_shared_prices_agg) / len(mf_couple_shared_prices_agg) if mf_couple_shared_prices_agg else 0, len(mf_couple_shared_prices_agg)),
        "Žena (deli veliki krevet sa Ž)": (sum(ff_sharer_prices_agg) / len(ff_sharer_prices_agg) if ff_sharer_prices_agg else 0, len(ff_sharer_prices_agg)),
        "Muškarac (deli veliki krevet sa M)": (sum(mm_sharer_prices_agg) / len(mm_sharer_prices_agg) if mm_sharer_prices_agg else 0, len(mm_sharer_prices_agg)),
        "Ženski Individualac (deli žensku sobu)": (sum(f_ind_prices_agg) / len(f_ind_prices_agg) if f_ind_prices_agg else 0, len(f_ind_prices_agg)),
        "Muški Individualac (deli mušku sobu)": (sum(m_ind_prices_agg) / len(m_ind_prices_agg) if m_ind_prices_agg else 0, len(m_ind_prices_agg))
    })

    final_total_accommodated_guests = sum(item['guests_accommodated'] for item in allocation)
    final_remaining_unallocated = (remaining_solo_guests +
                                   remaining_exclusive_couples_guests +
                                   remaining_female_individuals_generic + 
                                   remaining_male_individuals_generic +   
                                   remaining_mf_pairs * 2)

    final_total_income_from_rooms = sum(item['room_income'] for item in allocation)
    final_total_income_from_meals = sum(item['meal_income'] for item in allocation)
    final_total_rooms_used_count = len(allocation)
    total_room_income_for_num_days_calc = final_total_income_from_rooms * num_days
    total_meal_income_for_num_days_calc = final_total_income_from_meals * num_days
    avg_achieved_price_per_bed_room_only_calc = final_total_income_from_rooms / final_total_accommodated_guests if final_total_accommodated_guests > 0 else 0.0
    total_hotel_capacity_beds_val_overall = sum(room['single_beds'] * 1 + room['double_beds'] * 2 + room['sofa_beds'] * 2 for room in individual_rooms_data)
    total_physical_rooms_in_hotel_val_overall = len(individual_rooms_data)
    avg_price_per_guest_incl_meals_calc = (final_total_income_from_rooms + final_total_income_from_meals) / final_total_accommodated_guests if final_total_accommodated_guests > 0 else 0.0
    avg_price_per_occupied_room_calc = final_total_income_from_rooms / final_total_rooms_used_count if final_total_rooms_used_count > 0 else 0.0
    final_total_lost_bed_capacity_calc = sum(room_res['wasted_slots_on_beds_final'] for room_res in allocation)

    status_msg_final = "unknown"
    if total_guests_overall == 0: status_msg_final = "no_guests_requested"
    elif num_available_rooms_total_initially == 0: status_msg_final = "no_rooms_available"
    elif final_total_accommodated_guests == 0:
        if num_rooms_within_budget_overall == 0 and num_available_rooms_total_initially > 0: status_msg_final = "no_rooms_within_budget_and_no_guests"
        else: status_msg_final = "no_guests_accommodated"
    elif final_total_accommodated_guests > 0 and final_remaining_unallocated == 0 and final_total_accommodated_guests == total_guests_overall:
        all_used_rooms_over_budget_flag_check = False
        if final_total_rooms_used_count > 0 :
            all_used_rooms_over_budget_flag_check = all(room_in_alloc_check['over_max_budget'] for room_in_alloc_check in allocation)
        if all_used_rooms_over_budget_flag_check and num_rooms_within_budget_overall == 0 : status_msg_final = "all_rooms_over_budget"
        else: status_msg_final = "success"
    elif final_total_accommodated_guests > 0 and final_remaining_unallocated > 0: status_msg_final = "partial_success"
    elif final_total_accommodated_guests > 0 and final_remaining_unallocated < 0 :
        st.error(f"Interna greška: Negativan broj nealociranih gostiju ({final_remaining_unallocated}). Proverite logiku brojanja.")
        status_msg_final = "error_counting_unallocated"

    return (allocation, final_total_income_from_rooms, final_total_income_from_meals,
            final_total_accommodated_guests, final_remaining_unallocated, status_msg_final,
            avg_achieved_price_per_bed_room_only_calc, final_total_rooms_used_count,
            num_rooms_within_budget_overall, 
            num_available_rooms_total_initially,
            total_available_beds_capacity_overall, 
            total_hotel_capacity_beds_val_overall, avg_price_per_guest_incl_meals_calc,
            avg_price_per_occupied_room_calc, total_physical_rooms_in_hotel_val_overall,
            total_room_income_for_num_days_calc, total_meal_income_for_num_days_calc,
            avg_prices_by_guest_type_with_count_report,
            final_total_lost_bed_capacity_calc
            )

# --- Glavna aplikacija ---
def main():
    ALLOCATION_TABLE_HEIGHT = st.session_state.get('allocation_table_height', 550)

    st.set_page_config(layout="wide", page_title="Optimizacija Gostiju v3.3.2") 
    st.markdown("<h5 style='font-size: 22px; color: #0056b3; text-align: center;'>🏦 Optimizacija Rasporeda Gostiju</h1>", unsafe_allow_html=True)
    st.markdown("---")

    if 'individual_rooms' not in st.session_state:
        st.session_state.individual_rooms = []
    if 'global_meal_prices' not in st.session_state:
        st.session_state.global_meal_prices = {'breakfast': 10.0, 'lunch': 15.0, 'dinner': 20.0}

    if st.session_state.individual_rooms:
        for i, room_data_loop in enumerate(st.session_state.individual_rooms):
            if 'base_type' not in room_data_loop or not room_data_loop.get('base_type'):
                st.session_state.individual_rooms[i]['base_type'] = get_base_type_from_name(room_data_loop['name'])
            if 'priority' in st.session_state.individual_rooms[i]: 
                del st.session_state.individual_rooms[i]['priority']

    if not st.session_state.individual_rooms and 'predefined_rooms_added_v332' not in st.session_state: 
        predefined_individual_rooms = [ 
            {'id': 'S-001', 'name': 'King | K1', 'base_type': 'King', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-002', 'name': 'Exec | K1+T2+S1', 'base_type': 'Exec', 'single_beds': 2, 'double_beds': 1, 'sofa_beds': 1, 'price': 200.0, 'is_available': True}, 
            {'id': 'S-003', 'name': 'King | K1', 'base_type': 'King', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-004', 'name': 'Twin | T2', 'base_type': 'Twin', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-005', 'name': 'King | K1', 'base_type': 'King', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-101', 'name': 'Junr | K1+S1', 'base_type': 'Junr', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'is_available': True},
            {'id': 'S-102', 'name': 'Junr | K1+S1', 'base_type': 'Junr', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'is_available': True},
            {'id': 'S-103', 'name': 'King | K1', 'base_type': 'King', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-104', 'name': 'Twin | T2', 'base_type': 'Twin', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-105', 'name': 'Twin | T2', 'base_type': 'Twin', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-106', 'name': 'Twin | T2', 'base_type': 'Twin', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-107', 'name': 'King | K1', 'base_type': 'King', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-108', 'name': 'King | K1', 'base_type': 'King', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-109', 'name': 'King | K1+S1', 'base_type': 'King', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 130.0, 'is_available': True}, 
            {'id': 'S-110', 'name': 'Exec | K1+T1+S1', 'base_type': 'Exec', 'single_beds': 1, 'double_beds': 1, 'sofa_beds': 1, 'price': 200.0, 'is_available': True}, 
            {'id': 'S-111', 'name': 'Junr | K1+S1', 'base_type': 'Junr', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'is_available': True},
            {'id': 'S-201', 'name': 'Junr | K1+S1', 'base_type': 'Junr', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'is_available': True},
            {'id': 'S-202', 'name': 'Exec | K1+T2+S1', 'base_type': 'Exec', 'single_beds': 2, 'double_beds': 1, 'sofa_beds': 1, 'price': 200.0, 'is_available': True},
            {'id': 'S-203', 'name': 'King | K1', 'base_type': 'King', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-204', 'name': 'Twin | T2', 'base_type': 'Twin', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-205', 'name': 'Twin | T2', 'base_type': 'Twin', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-206', 'name': 'Twin | T2', 'base_type': 'Twin', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-207', 'name': 'King | K1', 'base_type': 'King', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-208', 'name': 'King | K1', 'base_type': 'King', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'is_available': True},
            {'id': 'S-209', 'name': 'King | K1+S1', 'base_type': 'King', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 130.0, 'is_available': True}, 
            {'id': 'S-210', 'name': 'Exec | K1+T1+S1', 'base_type': 'Exec', 'single_beds': 1, 'double_beds': 1, 'sofa_beds': 1, 'price': 200.0, 'is_available': True},
            {'id': 'S-211', 'name': 'Junr | K1+S1', 'base_type': 'Junr', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'is_available': True},
            {'id': 'S-301', 'name': 'Royl | K1+T2+S1', 'base_type': 'Royl', 'single_beds': 2, 'double_beds': 1, 'sofa_beds': 1, 'price': 240.0, 'is_available': True},
            {'id': 'S-302', 'name': 'Royl | K1+S1', 'base_type': 'Royl', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 240.0, 'is_available': True},
            {'id': 'S-303', 'name': 'Junr | K1+S1', 'base_type': 'Junr', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'is_available': True},
            {'id': 'S-304', 'name': 'Royl | K1+S1', 'base_type': 'Royl', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 240.0, 'is_available': True},
            {'id': 'S-305', 'name': 'Royl | K1+T2+S1', 'base_type': 'Royl', 'single_beds': 2, 'double_beds': 1, 'sofa_beds': 1, 'price': 240.0, 'is_available': True},
        ]
        st.session_state.individual_rooms.extend(predefined_individual_rooms)
        st.session_state.predefined_rooms_added_v332 = True 
        for i, room_data_loop in enumerate(st.session_state.individual_rooms):
            if 'base_type' not in room_data_loop or not room_data_loop.get('base_type'):
                st.session_state.individual_rooms[i]['base_type'] = get_base_type_from_name(room_data_loop['name'])

    st.sidebar.header("Kontrole i Podešavanja")
    allocation_button = st.sidebar.button("Pokreni Optimizaciju Rasporeda", type="primary", use_container_width=True, key="run_optimization_button")
    
   
    _s_max_price = st.session_state.get('last_max_price_val', 80.0)
    max_price_per_guest_val = st.sidebar.number_input(
        "Ciljna maksimalna ukupna cena po gostu (smeštaj + obroci, €)",
        min_value=0.0, value=_s_max_price, step=1.0, format="%.2f",
        help="Ciljna cena po gostu (računato na maksimalni kapacitet sobe).",
        key="max_price_main_input"
    )
    
    with st.sidebar.container():
        
        _s_num_days = st.session_state.get('last_num_days_val', 1)
        num_days_val = st.number_input("Broj dana boravka", min_value=1, value=_s_num_days, step=1, key="num_days_main_input")
   
    
    col_bf, col_lu, col_di = st.sidebar.columns(3)
    with col_bf:
        _s_bf_check = st.session_state.get('last_bf_check_val', True)
        breakfast_chosen_val = st.checkbox("Doručak", value=_s_bf_check, key="bf_main_check")
    with col_lu:
        _s_lu_check = st.session_state.get('last_lu_check_val', False)
        lunch_chosen_val = st.checkbox("Ručak", value=_s_lu_check, key="lu_main_check")
    with col_di:
        _s_di_check = st.session_state.get('last_di_check_val', True)
        dinner_chosen_val = st.checkbox("Večera", value=_s_di_check, key="di_main_check")
    st.sidebar.markdown("---")    
    

    with st.sidebar.container():
        st.subheader("Parametri Gostiju")
        total_guests_input_val = st.number_input(
            "Ukupan broj gostiju za raspored", min_value=0,
            value=st.session_state.get('last_total_guests_input_val', 15),
            step=1, key="total_guests_main_input"
        )

        def get_current_widget_val(widget_key, last_val_key, default_val=0):
            val = st.session_state.get(widget_key, st.session_state.get(last_val_key, default_val))
            return val if val is not None else default_val

        _cv_solo = get_current_widget_val("solo_guests_main_input", 'last_solo_guests_val', 0)
        _cv_excl_couples_num = get_current_widget_val("exclusive_couples_main_input", 'last_exclusive_couples_num_val', 0)
        _cv_fem_ind = get_current_widget_val("female_individuals_input", 'last_female_individuals_val', 0)
        _cv_male_ind = get_current_widget_val("male_individuals_input", 'last_male_individuals_val', 0)
        _cv_fem_sharers = get_current_widget_val("female_bed_sharers_input_widget", 'last_female_bed_sharers_val', 0)
        _cv_male_sharers = get_current_widget_val("male_bed_sharers_input_widget", 'last_male_bed_sharers_val', 0)
        _cv_mf_couples_num = get_current_widget_val("mf_couples_main_input", 'last_mf_couples_num_val', 0)

        live_sum_of_all_categories = (
            _cv_solo +
            _cv_excl_couples_num * 2 +
            _cv_fem_ind + _cv_male_ind +
            _cv_fem_sharers +
            _cv_male_sharers +
            _cv_mf_couples_num * 2
        )

        st.markdown("**Gosti koji NE DELE sobu):**")
       

        sum_others_for_solo = live_sum_of_all_categories - _cv_solo
        max_val_for_solo = min(total_guests_input_val, max(0, total_guests_input_val - sum_others_for_solo))
        solo_guests_val = st.number_input(
            "👨🏻‍💼 Solo gosti (zasebna soba)", min_value=0,
            max_value=max_val_for_solo if max_val_for_solo >= 0 else 0, 
            value=_cv_solo, step=1, key="solo_guests_main_input",
            help=f"Maksimalno za unos: {max_val_for_solo}."
        )

        sum_others_than_excl_couples = live_sum_of_all_categories - (_cv_excl_couples_num * 2)
        max_guests_for_excl_couples = max(0, total_guests_input_val - sum_others_than_excl_couples)
        max_val_for_excl_couples_num = min(total_guests_input_val // 2, max_guests_for_excl_couples // 2) if total_guests_input_val > 0 else 0
        exclusive_couples_num_input = st.number_input(
            "🥂 Ekskluzivni parovi (br. parova)", min_value=0,
            max_value=max_val_for_excl_couples_num if max_val_for_excl_couples_num >=0 else 0, 
            value=_cv_excl_couples_num, step=1, key="exclusive_couples_main_input",
            help=f"Maksimalno parova: {max_val_for_excl_couples_num}."
        )
        exclusive_couples_guests_val = exclusive_couples_num_input * 2

        st.markdown("**Gosti koji DELE SOBU (pol se ne meša):**")
        

        st.markdown("<span style='font-size: 0.9em;'>🙋🏻‍♂️ Individualci, ne dele krevet, dele sobu:</span>", unsafe_allow_html=True)
        col_indiv_f, col_indiv_m = st.columns(2)
        with col_indiv_f:
            sum_others_than_fem_ind = live_sum_of_all_categories - _cv_fem_ind
            max_val_for_fem_ind = min(total_guests_input_val, max(0, total_guests_input_val - sum_others_than_fem_ind))
            female_individuals_input_val = st.number_input(
                "Ž (br. osoba)", min_value=0,
                max_value=max_val_for_fem_ind if max_val_for_fem_ind >=0 else 0,
                value=_cv_fem_ind, step=1, key="female_individuals_input",
                help=f"Maksimalno: {max_val_for_fem_ind}."
            )
        with col_indiv_m:
            sum_others_than_male_ind = live_sum_of_all_categories - _cv_male_ind
            max_val_for_male_ind = min(total_guests_input_val, max(0, total_guests_input_val - sum_others_than_male_ind))
            male_individuals_input_val = st.number_input(
                "M (br. osoba)", min_value=0,
                max_value=max_val_for_male_ind if max_val_for_male_ind >=0 else 0,
                value=_cv_male_ind, step=1, key="male_individuals_input",
                help=f"Maksimalno: {max_val_for_male_ind}."
            )

        st.markdown("<span style='font-size: 0.9em;'>😉 Gosti koji dele i sobu i krevete:</span>", unsafe_allow_html=True)
        col_f_sharer, col_m_sharer = st.columns(2)
        with col_f_sharer:
            sum_others_than_fem_sharer = live_sum_of_all_categories - _cv_fem_sharers
            max_val_for_fem_sharer = min(total_guests_input_val, max(0, total_guests_input_val - sum_others_than_fem_sharer))
            female_bed_sharers_input_val = st.number_input(
                "Ž (br. osoba)", min_value=0,
                max_value=max_val_for_fem_sharer if max_val_for_fem_sharer >=0 else 0,
                value=_cv_fem_sharers, step=1, key="female_bed_sharers_input_widget",
                help=f"Maksimalno: {max_val_for_fem_sharer}."
            )
        with col_m_sharer:
            sum_others_than_male_sharer = live_sum_of_all_categories - _cv_male_sharers
            max_val_for_male_sharer = min(total_guests_input_val, max(0, total_guests_input_val - sum_others_than_male_sharer))
            male_bed_sharers_input_val = st.number_input(
                "M (br. osoba)", min_value=0,
                max_value=max_val_for_male_sharer if max_val_for_male_sharer >=0 else 0,
                value=_cv_male_sharers, step=1, key="male_bed_sharers_input_widget",
                help=f"Maksimalno: {max_val_for_male_sharer}."
            )

        st.markdown("<span style='font-size: 0.9em;'>👫 MŽ Parovi (dele sobu samo sa drugim MŽ parovima):</span>", unsafe_allow_html=True)
        sum_others_than_mf_couples = live_sum_of_all_categories - (_cv_mf_couples_num * 2)
        max_guests_for_mf_couples = max(0, total_guests_input_val - sum_others_than_mf_couples)
        max_val_for_mf_couples_num = min(total_guests_input_val // 2, max_guests_for_mf_couples // 2) if total_guests_input_val > 0 else 0
        mf_couples_input_val = st.number_input(
            "MŽ Parovi (br. parova)", min_value=0,
            max_value=max_val_for_mf_couples_num if max_val_for_mf_couples_num >=0 else 0,
            value=_cv_mf_couples_num, step=1, key="mf_couples_main_input",
            help=f"Maksimalno parova: {max_val_for_mf_couples_num}."
        )

        current_sum_of_all_guest_categories_final = (
            (solo_guests_val if solo_guests_val is not None else 0) +
            (exclusive_couples_guests_val if exclusive_couples_guests_val is not None else 0) +
            (female_individuals_input_val if female_individuals_input_val is not None else 0) +
            (male_individuals_input_val if male_individuals_input_val is not None else 0) +
            (female_bed_sharers_input_val if female_bed_sharers_input_val is not None else 0) +
            (male_bed_sharers_input_val if male_bed_sharers_input_val is not None else 0) +
            (mf_couples_input_val * 2 if mf_couples_input_val is not None else 0)
        )

        st.markdown(f"<p style='font-size: 0.9em; color: #555;'>Provera: Uneto kategorija <strong style='color: #0061b3;'>{current_sum_of_all_guest_categories_final}</strong> / Traženo ukupno: <strong style='color: #0061b3;'>{total_guests_input_val}</strong></p>", unsafe_allow_html=True)

        can_run_allocation_flag = True
        if total_guests_input_val > 0 and current_sum_of_all_guest_categories_final != total_guests_input_val:
            st.sidebar.error(f"Zbir kategorija ({current_sum_of_all_guest_categories_final}) ne odgovara Ukupnom broju gostiju ({total_guests_input_val})!")
            can_run_allocation_flag = False
        elif total_guests_input_val == 0 and current_sum_of_all_guest_categories_final > 0:
            st.sidebar.error(f"Ukupan broj gostiju je 0, ali uneli ste {current_sum_of_all_guest_categories_final} gostiju u kategorije.")
            can_run_allocation_flag = False
        elif total_guests_input_val > 0 and current_sum_of_all_guest_categories_final == 0 and not st.session_state.get("run_optimization_button_pressed_flag", False):
            st.sidebar.warning("Definisan je ukupan broj gostiju, ali nijedna kategorija nije popunjena.")

    st.sidebar.markdown("---")
    st.sidebar.subheader("Prioriteti Tipova Soba (za Alokaciju)")
    st.sidebar.caption("Niža vrednost = viši prioritet.")

    initial_hardcoded_priorities = {
        'King': 1, 'Twin': 1, 'Junr': 1, 'Exec': 1, 'Royl': 500, 'Unknown': 100
    }
    general_default_priority_for_unspecified_types = max(initial_hardcoded_priorities.values()) + 1

    room_types_for_priority_setting = []
    if 'individual_rooms' in st.session_state and st.session_state.individual_rooms:
        room_types_for_priority_setting = sorted(list(set(room.get('base_type', 'Unknown') for room in st.session_state.individual_rooms if room.get('base_type'))))
        if not room_types_for_priority_setting and st.session_state.individual_rooms:
             room_types_for_priority_setting = sorted(list(set(get_base_type_from_name(room['name']) for room in st.session_state.individual_rooms)))

    if 'room_type_priorities' not in st.session_state:
        new_priorities = {}
        for rt in room_types_for_priority_setting:
            new_priorities[rt] = initial_hardcoded_priorities.get(rt, general_default_priority_for_unspecified_types)
        st.session_state.room_type_priorities = new_priorities

    temp_room_type_priorities = st.session_state.room_type_priorities.copy()
    for r_type in room_types_for_priority_setting:
        if r_type not in temp_room_type_priorities:
            temp_room_type_priorities[r_type] = initial_hardcoded_priorities.get(r_type, general_default_priority_for_unspecified_types)

    active_room_types_set = set(room_types_for_priority_setting)
    keys_to_remove_from_prio = [key for key in temp_room_type_priorities if key not in active_room_types_set]
    for key_rem in keys_to_remove_from_prio:
        if key_rem in temp_room_type_priorities:
            del temp_room_type_priorities[key_rem]

    for r_type in room_types_for_priority_setting:
        default_value_for_input = temp_room_type_priorities.get(r_type, initial_hardcoded_priorities.get(r_type, general_default_priority_for_unspecified_types))
        disabled_royl_priority_input = (r_type == 'Royl')
        help_text_priority = "Prioritet za 'Royl' se interno postavlja na najniži u algoritmu i ovaj unos se ignoriše." if disabled_royl_priority_input else "Niža vrednost = viši prioritet."
        if r_type == 'King':
            help_text_priority += " King sobe imaju dodatni implicitni prioritet za Solo goste i Ekskluzivne parove."

        temp_room_type_priorities[r_type] = st.sidebar.number_input(
            f"Prioritet za '{r_type}'", min_value=1, max_value=500,
            value=int(default_value_for_input),
            step=1, key=f"type_prio_{r_type}",
            disabled=disabled_royl_priority_input,
            help=help_text_priority
        )
    st.session_state.room_type_priorities = temp_room_type_priorities

    st.sidebar.markdown("---")
    


    new_alloc_table_height = st.sidebar.number_input("Podesi visinu tabele rasporeda (px)", min_value=200, max_value=2000, value=ALLOCATION_TABLE_HEIGHT, step=50, key="alloc_table_height_input")
    if new_alloc_table_height != ALLOCATION_TABLE_HEIGHT:
        st.session_state.allocation_table_height = new_alloc_table_height
        st.rerun()

    st.sidebar.markdown("---")
    

    tab_hotel_management, tab_reports = st.tabs(["⚙️ Upravljanje Hotelom", "📊 Izveštaji i Optimizacija"])

    with tab_hotel_management:
        st.markdown("#### ⚙️ Upravljanje Hotelom")
        st.write("Ovde možete konfigurisati pojedinačne sobe i cene obroka.")
        tab_available_rooms, tab_edit_rooms_and_availability, tab_meal_settings = st.tabs([
            "🔢 Pregled Soba", "✏️ Izmeni Detalje Soba", "🍽️ Postavke Cena Obroka"
        ])

        with tab_available_rooms:
            st.markdown("##### 🔢 Brza Izmena Dostupnosti Soba")
            if not st.session_state.individual_rooms:
                st.info("Nema definisanih soba.")
            else:
                sorted_rooms_display = sorted(st.session_state.individual_rooms, key=lambda r: r.get('id', ''))
                num_columns = 6
                cols = st.columns(num_columns)
                for i, room_iter in enumerate(sorted_rooms_display):
                    with cols[i % num_columns]:
                        with st.container(border=True):
                            current_availability = room_iter.get('is_available', True)
                            checkbox_key = f"availability_checkbox_{room_iter.get('id','N/A')}"
                            info_col, cb_col = st.columns([0.7, 0.3])
                            with info_col:
                                st.markdown(f"<div style='font-size: 0.85em; font-weight: bold; padding-top: 6px;'>{room_iter.get('id','N/A')}</div>", unsafe_allow_html=True)
                            with cb_col:
                                st.checkbox(" ", value=current_availability, key=checkbox_key, on_change=toggle_room_availability_callback, args=(room_iter.get('id'), checkbox_key), help=f"Dostupnost za: {room_iter.get('id','N/A')} ({room_iter.get('name','N/A')})")

            st.markdown("---")
            st.markdown("##### Detaljan tabelarni pregled svih soba")
            def highlight_unavailable_rows(row):
                color = 'mistyrose'; default_style = [''] * len(row)
                if row['Dostupna'] == "Ne": return [f'background-color: {color}'] * len(row)
                return default_style

            if st.session_state.individual_rooms:
                rooms_df_data_display = []
                for r_display in st.session_state.individual_rooms:
                    rooms_df_data_display.append({
                        "ID Sobe": r_display.get('id','N/A'), "Naziv Sobe": r_display.get('name','N/A'),
                        "Osnovni Tip": r_display.get('base_type', 'N/A'),
                        "TWIN Kreveti": r_display.get('single_beds',0), "KING Kreveti": r_display.get('double_beds',0),
                        "SOFA Kreveti": r_display.get('sofa_beds',0),
                        "Maks. Kapacitet": r_display.get('single_beds',0)*1 + r_display.get('double_beds',0)*2 + r_display.get('sofa_beds',0)*2,
                        "Cena (€)": f"{r_display.get('price',0.0):.2f}",
                        "Dostupna": "Da" if r_display.get('is_available', True) else "Ne"
                    })
                df_rooms = pd.DataFrame(rooms_df_data_display)
                cols_order = ["ID Sobe", "Naziv Sobe", "Osnovni Tip", "TWIN Kreveti", "KING Kreveti", "SOFA Kreveti", "Maks. Kapacitet", "Cena (€)", "Dostupna"]
                df_rooms_display_final = df_rooms[[col for col in cols_order if col in df_rooms.columns]]
                styled_df_rooms = df_rooms_display_final.style.apply(highlight_unavailable_rows, axis=1)
                st.dataframe(styled_df_rooms, use_container_width=True, hide_index=True, height=ALLOCATION_TABLE_HEIGHT)
            elif not st.session_state.individual_rooms: st.info("Nema definisanih soba za detaljan prikaz.")


        with tab_edit_rooms_and_availability:
            st.markdown("#### ✏️ Izmeni Detalje Soba")
            if not st.session_state.individual_rooms: st.info("Nema soba za izmenu.")
            else:
                sorted_rooms_edit = sorted(st.session_state.individual_rooms, key=lambda r: r.get('id', ''))
                for i_room_edit_tab, room_to_edit_tab in enumerate(sorted_rooms_edit):
                    availability_status_text = "Dostupna" if room_to_edit_tab.get('is_available', True) else "Nije dostupna"
                    exp_title_tab = f"{room_to_edit_tab.get('name','N/A')} (Tip: {room_to_edit_tab.get('base_type', 'N/A')}, ID: {room_to_edit_tab.get('id','N/A')}) - Status: {availability_status_text}"
                    with st.expander(exp_title_tab):
                        form_key_tab = f"form_edit_tab_{room_to_edit_tab.get('id','N/A')}_{i_room_edit_tab}"
                        with st.form(form_key_tab):
                            col_form_edit_1, col_form_edit_2 = st.columns(2)
                            with col_form_edit_1:
                                st.text_input("ID Sobe", value=room_to_edit_tab.get('id','N/A'), disabled=True, key=f"text_id_edit_val_{room_to_edit_tab.get('id','N/A')}_{i_room_edit_tab}")
                                new_name_val_form = st.text_input("Naziv", value=room_to_edit_tab.get('name','N/A'), key=f"text_name_edit_val_{room_to_edit_tab.get('id','N/A')}_{i_room_edit_tab}")
                                new_price_val_form = st.number_input("Cena (€)", value=room_to_edit_tab.get('price',0.0), min_value=0.0, step=0.01, format="%.2f", key=f"num_p_edit_val_{room_to_edit_tab.get('id','N/A')}_{i_room_edit_tab}")
                            with col_form_edit_2:
                                new_single_beds_val_form = st.number_input("Singl krevet", value=room_to_edit_tab.get('single_beds',0), min_value=0, step=1, key=f"num_s_edit_val_{room_to_edit_tab.get('id','N/A')}_{i_room_edit_tab}")
                                new_double_beds_val_form = st.number_input("King size", value=room_to_edit_tab.get('double_beds',0), min_value=0, step=1, key=f"num_d_edit_val_{room_to_edit_tab.get('id','N/A')}_{i_room_edit_tab}")
                                new_sofa_beds_val_form = st.number_input("Sofa", value=room_to_edit_tab.get('sofa_beds',0), min_value=0, step=1, key=f"num_sf_edit_val_{room_to_edit_tab.get('id','N/A')}_{i_room_edit_tab}")

                            st.caption(f"Dostupnost se menja u tabu 'Pregled Soba'. Trenutni status: {availability_status_text}")
                            st.info(f"Globalne cene obroka: D={st.session_state.global_meal_prices['breakfast']:.2f}€, R={st.session_state.global_meal_prices['lunch']:.2f}€, V={st.session_state.global_meal_prices['dinner']:.2f}€.")
                            current_user_set_priority = st.session_state.get('room_type_priorities', {}).get(room_to_edit_tab.get('base_type', 'N/A'), 'Nije definisan')
                            priority_display_text = f"Korisnički prioritet za tip '{room_to_edit_tab.get('base_type', 'N/A')}' je: {current_user_set_priority}."
                            if room_to_edit_tab.get('base_type') == 'Royl':
                                priority_display_text += " (Interno, 'Royl' uvek ima najniži prioritet u alokaciji)."
                            st.caption(priority_display_text)

                            if st.form_submit_button("Ažuriraj Detalje"):
                                if (new_single_beds_val_form + new_double_beds_val_form + new_sofa_beds_val_form) == 0: st.error("Soba mora imati barem jedan krevet.")
                                else:
                                    idx_to_update_form = next((k_idx_form for k_idx_form, r_find_form in enumerate(st.session_state.individual_rooms) if r_find_form.get('id') == room_to_edit_tab.get('id')), -1)
                                    if idx_to_update_form != -1:
                                        st.session_state.individual_rooms[idx_to_update_form].update({
                                            'name': new_name_val_form,
                                            'base_type': get_base_type_from_name(new_name_val_form),
                                            'single_beds': int(new_single_beds_val_form),
                                            'double_beds': int(new_double_beds_val_form), 'sofa_beds': int(new_sofa_beds_val_form),
                                            'price': float(new_price_val_form)
                                        })
                                        active_types = sorted(list(set(room.get('base_type', 'Unknown') for room in st.session_state.individual_rooms if room.get('base_type'))))
                                        if not active_types and st.session_state.individual_rooms: 
                                            active_types = sorted(list(set(get_base_type_from_name(room['name']) for room in st.session_state.individual_rooms)))
                                        current_priorities = st.session_state.get('room_type_priorities', {})
                                        for r_type_active in active_types:
                                            if r_type_active not in current_priorities:
                                                current_priorities[r_type_active] = initial_hardcoded_priorities.get(r_type_active, general_default_priority_for_unspecified_types)
                                        st.session_state.room_type_priorities = current_priorities
                                        st.success(f"Detalji sobe '{new_name_val_form}' ažurirani."); st.rerun()
                                    else: st.error("Greška: Soba nije pronađena za ažuriranje.")
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
        st.markdown("#### 📊 Izveštaji i Optimizacija")
        if allocation_button:
            st.session_state.run_optimization_button_pressed_flag = True

            if not can_run_allocation_flag:
                st.error("Molimo ispravite unos parametara gostiju u sidebar-u.")
            elif not st.session_state.individual_rooms or not any(r.get('is_available', True) for r in st.session_state.individual_rooms):
                st.error("Nema definisanih ili dostupnih soba za alokaciju.")
            elif total_guests_input_val == 0 and current_sum_of_all_guest_categories_final == 0 :
                st.info("Nema gostiju za raspored (ukupan broj gostiju i sve kategorije su 0).")
                keys_to_clear_results = [
                    'last_allocation_results', 'last_total_room_income', 'last_total_meal_income',
                    'last_total_accommodated', 'last_remaining_guests', 'last_status_message',
                    'last_avg_achieved_price_per_bed', 'last_total_rooms_used_count',
                    'last_num_rooms_within_budget', 'last_num_available_rooms_initially',
                    'last_total_available_beds_capacity', 'last_total_hotel_capacity_beds',
                    'last_avg_price_per_guest_incl_meals', 'last_avg_price_per_occupied_room',
                    'last_total_physical_rooms_in_hotel', 'last_total_room_income_for_num_days',
                    'last_total_meal_income_for_num_days', 'last_avg_prices_by_guest_type',
                    'last_lost_bed_capacity'
                ]
                for key_clr in keys_to_clear_results:
                    if key_clr in st.session_state: del st.session_state[key_clr]
                if st.session_state.get('last_total_guests_input_val', 0) > 0 and total_guests_input_val == 0:
                     st.session_state.last_total_guests_input_val = 0
            else:
                st.info("Pokrećem optimizaciju rasporeda...")
                safe_solo_guests_val = solo_guests_val if solo_guests_val is not None else 0
                safe_exclusive_couples_guests_val = exclusive_couples_guests_val if exclusive_couples_guests_val is not None else 0
                safe_female_individuals_input_val = female_individuals_input_val if female_individuals_input_val is not None else 0
                safe_male_individuals_input_val = male_individuals_input_val if male_individuals_input_val is not None else 0
                safe_female_bed_sharers_input_val = female_bed_sharers_input_val if female_bed_sharers_input_val is not None else 0
                safe_male_bed_sharers_input_val = male_bed_sharers_input_val if male_bed_sharers_input_val is not None else 0
                safe_mf_couples_input_val = mf_couples_input_val if mf_couples_input_val is not None else 0

                room_type_priorities_for_alloc = st.session_state.get('room_type_priorities', {})

                (res_allocation, res_room_income, res_meal_income,
                res_total_accommodated, res_remaining_guests, res_status_msg,
                res_avg_price_bed, res_rooms_used, res_rooms_in_budget,
                res_num_avail_rooms_initially,
                res_avail_beds_cap, res_hotel_beds,
                res_avg_price_guest_total, res_avg_price_room,
                res_phys_rooms, res_room_income_days, res_meal_income_days,
                avg_prices_by_type_result,
                res_lost_bed_capacity
                ) = perform_allocation(
                    total_guests_input_val,
                    safe_solo_guests_val,
                    safe_exclusive_couples_guests_val,
                    safe_female_individuals_input_val,
                    safe_male_individuals_input_val,
                    safe_female_bed_sharers_input_val,
                    safe_male_bed_sharers_input_val,
                    safe_mf_couples_input_val,
                    max_price_per_guest_val,
                    breakfast_chosen_val, lunch_chosen_val, dinner_chosen_val,
                    st.session_state.individual_rooms, st.session_state.global_meal_prices, num_days_val,
                    room_type_priorities_for_alloc
                )

                st.session_state.last_total_guests_input_val = total_guests_input_val
                st.session_state.last_solo_guests_val = safe_solo_guests_val
                st.session_state.last_exclusive_couples_num_val = exclusive_couples_num_input if exclusive_couples_num_input is not None else 0
                st.session_state.last_female_individuals_val = safe_female_individuals_input_val
                st.session_state.last_male_individuals_val = safe_male_individuals_input_val
                st.session_state.last_female_bed_sharers_val = safe_female_bed_sharers_input_val
                st.session_state.last_male_bed_sharers_val = safe_male_bed_sharers_input_val
                st.session_state.last_mf_couples_num_val = safe_mf_couples_input_val
                st.session_state.last_num_days_val = num_days_val
                st.session_state.last_bf_check_val = breakfast_chosen_val
                st.session_state.last_lu_check_val = lunch_chosen_val
                st.session_state.last_di_check_val = dinner_chosen_val
                st.session_state.last_max_price_val = max_price_per_guest_val
                st.session_state.last_allocation_results = res_allocation
                st.session_state.last_total_room_income = res_room_income
                st.session_state.last_total_meal_income = res_meal_income
                st.session_state.last_total_accommodated = res_total_accommodated
                st.session_state.last_remaining_guests = res_remaining_guests
                st.session_state.last_status_message = res_status_msg
                st.session_state.last_avg_achieved_price_per_bed = res_avg_price_bed
                st.session_state.last_total_rooms_used_count = res_rooms_used
                st.session_state.last_num_rooms_within_budget = res_rooms_in_budget
                st.session_state.last_num_available_rooms_initially = res_num_avail_rooms_initially
                st.session_state.last_total_available_beds_capacity = res_avail_beds_cap
                st.session_state.last_total_hotel_capacity_beds = res_hotel_beds
                st.session_state.last_avg_price_per_guest_incl_meals = res_avg_price_guest_total
                st.session_state.last_avg_price_per_occupied_room = res_avg_price_room
                st.session_state.last_total_physical_rooms_in_hotel = res_phys_rooms
                st.session_state.last_total_room_income_for_num_days = res_room_income_days
                st.session_state.last_total_meal_income_for_num_days = res_meal_income_days
                st.session_state.last_avg_prices_by_guest_type = avg_prices_by_type_result
                st.session_state.last_lost_bed_capacity = res_lost_bed_capacity
                st.rerun()

        if st.session_state.get('last_total_guests_input_val') is not None:
            st.markdown("---")
            ls_res_disp = st.session_state

            if ls_res_disp.get('last_status_message') == "no_guests_requested" and ls_res_disp.get('last_total_guests_input_val', -1) == 0:
                st.info("Nije bilo zahteva za smeštaj gostiju (ukupan broj gostiju je 0).")
            elif 'last_allocation_results' in ls_res_disp :
                if ls_res_disp.get('last_total_guests_input_val',0) > 0 or ls_res_disp.get('last_total_accommodated',0) > 0 or st.session_state.get("run_optimization_button_pressed_flag", False) :
                    st.markdown("#### Detaljan Izveštaj Rasporeda")
                    status_msg_display = ls_res_disp.get('last_status_message', 'unknown')
                    if status_msg_display == "success": st.success(f"Uspešno je smešteno svih {ls_res_disp.get('last_total_accommodated',0)} od traženih {ls_res_disp.get('last_total_guests_input_val',0)} gostiju!")
                    elif status_msg_display == "partial_success": st.warning(f"Delimično uspešno: Smešteno je {ls_res_disp.get('last_total_accommodated',0)} od traženih {ls_res_disp.get('last_total_guests_input_val',0)} gostiju. {ls_res_disp.get('last_remaining_guests',0)} gostiju nije smešteno.")
                    elif status_msg_display == "no_rooms_available": st.error("Nijedna soba nije dostupna za alokaciju.")
                    elif status_msg_display == "no_guests_accommodated": st.error("Nijedan gost nije mogao biti smešten sa trenutnim parametrima i dostupnim sobama.")
                    elif status_msg_display == "no_rooms_within_budget_and_no_guests" : st.error(f"Nijedna dostupna soba ne zadovoljava budžet ({st.session_state.get('last_max_price_val', 0):.2f} €/gost) i nijedan gost nije smešten.")
                    elif status_msg_display == "all_rooms_over_budget": st.warning(f"Svi gosti su smešteni, ali sve korišćene sobe premašuju postavljeni budžet po gostu ({st.session_state.get('last_max_price_val', 0):.2f} €), računato na maksimalni kapacitet sobe.")
                    else: st.info(f"Status alokacije: {status_msg_display}")

                    naslov_sum_stil = "background-color: #edf7ff; color: #253f59; padding: 10px; border-radius: 5px; font-weight: bold;"
                    st.markdown(f"<div style='{naslov_sum_stil}'><h4 style='margin-bottom: 0;'>Sumarni pregled ključnih metrika:</h4></div>", unsafe_allow_html=True)
                    st.write("")
                    total_beds_used_for_kpi = ls_res_disp.get('last_total_accommodated',0)
                    actual_available_beds_capacity_for_kpi = ls_res_disp.get('last_total_available_beds_capacity', 0)
                    percentage_beds_used = (total_beds_used_for_kpi / actual_available_beds_capacity_for_kpi) * 100 if actual_available_beds_capacity_for_kpi > 0 else 0.0
                    beds_used_text = f"{total_beds_used_for_kpi} / {actual_available_beds_capacity_for_kpi} ({percentage_beds_used:.1f}%)"

                    summary_data_list_disp = [
                        {"Metrika": "Ukupan broj gostiju (po zahtevu)", "Vrednost": ls_res_disp.get('last_total_guests_input_val',0)},
                        {"Metrika": "Ukupan broj raspoloživih soba (na početku)", "Vrednost": ls_res_disp.get('last_num_available_rooms_initially', 'N/A')},
                        {"Metrika": "Broj dana boravka", "Vrednost": ls_res_disp.get('last_num_days_val',1)},
                        {"Metrika": "Ukupan kapacitet hotela (ležajevi u svim sobama)", "Vrednost": ls_res_disp.get('last_total_hotel_capacity_beds',0)},
                        {"Metrika": "Ukupno smešteno gostiju", "Vrednost": ls_res_disp.get('last_total_accommodated',0)},
                        #{"Metrika": f"Popunjenost dostupnih ležajeva", "Vrednost": beds_used_text},
                        #{"Metrika": "Propušteni (neiskorišćeni) ležajevi u KORIŠĆENIM sobama", "Vrednost": ls_res_disp.get('last_lost_bed_capacity',0)},
                        {"Metrika": "Dostupan kapacitet ležajeva (u raspoloživim sobama)", "Vrednost": ls_res_disp.get('last_total_available_beds_capacity',0)},
                        {"Metrika": "Gosti bez smeštaja", "Vrednost": ls_res_disp.get('last_remaining_guests',0)},        
                        {"Metrika": "Ukupno korišćeno soba", "Vrednost": ls_res_disp.get('last_total_rooms_used_count',0)},
                        {"Metrika": "Prosečna ostvarena cena po gostu (samo smeštaj)", "Vrednost": f"{ls_res_disp.get('last_avg_achieved_price_per_bed',0.0):,.2f} €"},
                        {"Metrika": f"Ukupan Prihod (Sobe, za {ls_res_disp.get('last_num_days_val',1)} dana)", "Vrednost": f"{ls_res_disp.get('last_total_room_income_for_num_days',0.0):,.2f} €"},
                        {"Metrika": "Prosečna cena po GOSTU (smeštaj + obroci)", "Vrednost": f"{ls_res_disp.get('last_avg_price_per_guest_incl_meals',0.0):,.2f} €"},
                        {"Metrika": f"Ukupan Prihod (Obroci, za {ls_res_disp.get('last_num_days_val',1)} dana)", "Vrednost": f"{ls_res_disp.get('last_total_meal_income_for_num_days',0.0):,.2f} €"},
                        {"Metrika": "Prosečna cena po zauzetoj SOBI (samo smeštaj)", "Vrednost": f"{ls_res_disp.get('last_avg_price_per_occupied_room',0.0):,.2f} €"},
                        {"Metrika": f"Ukupan Prihod (Sobe + Obroci, za {ls_res_disp.get('last_num_days_val',1)} dana)", "Vrednost": f"{(ls_res_disp.get('last_total_room_income_for_num_days',0.0) + ls_res_disp.get('last_total_meal_income_for_num_days',0.0)):,.2f} €"}
                    ]
                    TARGET_METRIC_NAME_STYLE = f"Ukupan Prihod (Sobe + Obroci, za {ls_res_disp.get('last_num_days_val',1)} dana)" 
                    TARGET_ITEM_BACKGROUND_STYLE = "#D4EDDA" 
                    TARGET_ITEM_METRIKA_FONT_COLOR_STYLE = "#1e241f" 
                    TARGET_ITEM_METRIKA_FONT_WEIGHT_STYLE = "bold"
                    TARGET_ITEM_VREDNOST_FONT_COLOR_STYLE = "#1e241f" 
                    TARGET_ITEM_VREDNOST_FONT_STYLE = "font-weight: bold;" 

                    TARGET_METRIC_NAME_STYLE_2 = "Prosečna cena po zauzetoj SOBI (samo smeštaj)" 
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

                    if 'last_avg_prices_by_guest_type' in ls_res_disp and ls_res_disp.get('last_avg_prices_by_guest_type'):
                        st.markdown("##### Prosečne efektivne cene po tipu gosta (sa obrocima)")
                        avg_prices_data_for_df_disp = []
                        guest_type_display_order_disp = [
                            "Solo Gost (zasebna soba)", "Ekskluzivni Par (po osobi, zasebna soba)",
                            "MŽ Par (po osobi, deli sobu sa MŽ)",
                            "Žena (deli veliki krevet sa Ž)",
                            "Muškarac (deli veliki krevet sa M)",
                            "Ženski Individualac (deli žensku sobu)", "Muški Individualac (deli mušku sobu)"
                        ]
                        for guest_type_key_disp in guest_type_display_order_disp:
                            avg_price_val_disp, guest_count_val_disp = ls_res_disp.last_avg_prices_by_guest_type.get(guest_type_key_disp, (0,0))
                            if guest_count_val_disp > 0:
                                avg_prices_data_for_df_disp.append({
                                    "Tip gosta": guest_type_key_disp, "Broj gostiju": guest_count_val_disp,
                                    "Prosečna efektivna cena/gost (€)": f"{avg_price_val_disp:.2f} €"
                                })
                        if avg_prices_data_for_df_disp:
                            df_avg_prices_display = pd.DataFrame(avg_prices_data_for_df_disp)
                            st.dataframe(df_avg_prices_display, use_container_width=True, hide_index=True)
                        elif ls_res_disp.get('last_total_accommodated',0) > 0 :
                            st.info("Nema podataka za prikaz prosečnih cena po tipu gosta (verovatno nijedan gost nije kategorisan).")
                        st.markdown("---")

                    if ls_res_disp.get('last_allocation_results') and (ls_res_disp.get('last_total_guests_input_val',0) > 0 or ls_res_disp.get('last_total_accommodated',0) > 0) :
                        st.markdown("#### Raspored Gostiju po Sobama")
                        allocation_display_data_list_render = []
                        for item_alloc_render in ls_res_disp.last_allocation_results:
                            total_room_revenue_per_day_item_render = item_alloc_render['room_income'] + item_alloc_render['meal_income']
                            over_budget_status_item_render = "DA" if item_alloc_render['over_max_budget'] else "NE"
                            gender_type_display_render = item_alloc_render.get('gender_type_final', 'N/A')
                            if gender_type_display_render == 'solo_exclusive': gender_type_display_render = 'Solo/Ekskl.'
                            elif gender_type_display_render == 'female': gender_type_display_render = 'Ženska'
                            elif gender_type_display_render == 'male': gender_type_display_render = 'Muška'
                            elif gender_type_display_render == 'mixed_mf_couples_only': gender_type_display_render = 'Mešovita (MŽ Parovi)'
                            elif gender_type_display_render is None : gender_type_display_render = "Prazna/Nedef."

                            allocation_display_data_list_render.append({
                                "ID Sobe": item_alloc_render['room_id'], "Naziv Sobe": item_alloc_render['room_name'],
                                "Aranžman Gostiju": item_alloc_render.get('guest_arrangement', 'N/A'),
                                "Tip Sobe (Pol)": gender_type_display_render,
                                "Smešteno Gostiju": item_alloc_render['guests_accommodated'],
                                "Prihod od Sobe (po danu)": f"{item_alloc_render['room_income']:.2f} €",
                                "Prihod od Obroka (po danu)": f"{item_alloc_render['meal_income']:.2f} €",
                                "Ukupan Prihod po Sobi (po danu)": f"{total_room_revenue_per_day_item_render:.2f} €",
                                f"Ukupan Prihod po Sobi (za {ls_res_disp.get('last_num_days_val',1)} dana)": f"{(total_room_revenue_per_day_item_render * ls_res_disp.get('last_num_days_val',1)):.2f} €",
                                "Efektivna Cena/Gost (€)": f"{item_alloc_render.get('effective_price_per_guest_actual', 0.0):.2f} €",
                                "Soba preko budžeta (max. kap.)": over_budget_status_item_render,
                                "Cena po gostu (max. kap. + obroci)": f"{item_alloc_render.get('total_price_per_guest_for_room_max_cap', 0.0):.2f} €"
                            })
                        df_allocation_to_display_render = pd.DataFrame(allocation_display_data_list_render)
                        desired_column_order_render = [
                            "ID Sobe", "Naziv Sobe", "Aranžman Gostiju", "Tip Sobe (Pol)", "Smešteno Gostiju",
                            "Prihod od Sobe (po danu)", "Prihod od Obroka (po danu)", "Ukupan Prihod po Sobi (po danu)",
                            f"Ukupan Prihod po Sobi (za {ls_res_disp.get('last_num_days_val',1)} dana)",
                            "Efektivna Cena/Gost (€)", "Soba preko budžeta (max. kap.)",
                            "Cena po gostu (max. kap. + obroci)"
                        ]
                        existing_columns_in_order_render = [col_render for col_render in desired_column_order_render if col_render in df_allocation_to_display_render.columns]
                        df_to_display_ordered_render = df_allocation_to_display_render[existing_columns_in_order_render]
                        def style_over_budget_column_alloc(val_style): return f'background-color: mistyrose' if val_style == "DA" else ''
                        def style_gender_type_alloc(val_style):
                            if val_style == 'Ženska': return 'background-color: #ffdde5'
                            elif val_style == 'Muška': return 'background-color: #dcf0ff'
                            elif val_style == 'Mešovita (MŽ Parovi)': return 'background-color: #e8e8e8'
                            elif val_style == 'Solo/Ekskl.': return 'background-color: #f5f5f5'
                            return ''
                        styled_allocation_df_render = df_to_display_ordered_render.style.map(style_over_budget_column_alloc, subset=["Soba preko budžeta (max. kap.)"]) \
                                                                                .map(style_gender_type_alloc, subset=["Tip Sobe (Pol)"])
                        st.dataframe(styled_allocation_df_render, use_container_width=True, hide_index=True, height=ALLOCATION_TABLE_HEIGHT)
                    elif ls_res_disp.get('last_total_guests_input_val',0) > 0 and not ls_res_disp.get('last_allocation_results') and ls_res_disp.get('last_status_message') != "no_guests_requested":
                        st.info("Nije bilo moguće generisati raspored sa trenutnim parametrima (nema zauzetih soba).")

            if 'run_optimization_button_pressed_flag' in st.session_state:
                del st.session_state['run_optimization_button_pressed_flag']

        elif not st.session_state.get("run_optimization_button_pressed_flag", False) and 'last_allocation_results' not in st.session_state :
            st.info("Unesite parametre u sidebar-u i kliknite na 'Pokreni Optimizaciju Rasporeda' da biste videli izveštaje.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"!!! DOŠLO JE DO GREŠKE PRILIKOM IZVRŠAVANJA main() FUNKCIJE !!!")
        print(f"Tip greške: {type(e).__name__}")
        print(f"Poruka greške: {str(e)}")
        print("Puni Traceback:")
        import traceback
        traceback.print_exc()