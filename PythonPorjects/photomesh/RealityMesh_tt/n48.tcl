tav_open world [lindex $argv 0]

#delete features and holes smaller than this area
set areathreshold 0.01

#delete coincident vertices when two vertices are closer than this distance
set coincidentthreshold 0.05

#delete collinear points when the angle is greater than this (in degrees)
set collinearthreshold 175

#delete spike points when the angle is less than this (in degrees)
set spikethreshold 5

proc calcdist {a b} {
    set abx [expr [lindex $b 0] - [lindex $a 0]]
    set aby [expr [lindex $b 1] - [lindex $a 1]]

    set hyp [expr sqrt($abx * $abx + $aby * $aby)] 

    return $hyp
}

proc calcangle {a b c} {
	set pi 3.1415926535897933
    set abx [expr [lindex $b 0] - [lindex $a 0]]
    set aby [expr [lindex $b 1] - [lindex $a 1]]
    set cbx [expr [lindex $b 0] - [lindex $c 0]]
    set cby [expr [lindex $b 1] - [lindex $c 1]]

    set dot [expr $abx * $cbx + $aby * $cby] 
    set cross [expr $abx * $cby - $aby * $cbx]

    set alpha [expr atan2($cross, $dot)]

    return [expr $alpha * 180 / $pi]
}

proc cleanareals {collinear spikes coincident} {
	global areathreshold
	global coincidentthreshold
	global collinearthreshold
	global spikethreshold
	set dfaces 0
	set dloops 0
	set dverts 0
	set dverts2 0
	set dverts3 0
	world arealapply a {
		if {[a has @angles_removed]} {
			continue
		}
		if {[a area] < $areathreshold} {
			a del -all *
			incr dfaces
			continue
		}
		world new_areal a2
		set attrlist [a listattr *]
		foreach attr $attrlist {
			a2 setattr -[a attrtype $attr] $attr [a get $attr]
		}

		for {set i 0} {$i < [a nloops]} {incr i} {
			a loop $i l
			if {[l area] < $areathreshold} { 
				incr dloops
				continue 
			}
			a2 new_loop l2
			set delnext 0
			for {set j 0} {$j < [l nverts]} {incr j} {
				if {$delnext == 1} {
					incr dverts3
					set delnext 0
					continue
				}
				l vertex [expr ($j - 1) % [l nverts]] v0
				l vertex $j v1
				l vertex [expr ($j + 1) % [l nverts]] v2
				set angle [calcangle [v0 coordinates] [v1 coordinates] [v2 coordinates]]
				set distance [calcdist [v0 coordinates] [v2 coordinates]]
				if {$coincident && $distance < $coincidentthreshold} {
					incr dverts3
					set delnext 1
					continue
				} elseif {$collinear && ($angle > $collinearthreshold || $angle < -$collinearthreshold)} {
					incr dverts
				} elseif {$spikes && $angle < $spikethreshold && $angle > -$spikethreshold} {
					incr dverts2
				} else {
					l2 add_vertex [lindex [v1 coordinates] 0] [lindex [v1 coordinates] 1] [lindex [v1 coordinates] 2]
				}
			}
		}
		a del -all *
		a2 set @angles_removed 1
	}

	world arealapply a {
		a del @angles_removed
	}

	puts "Removed $dfaces degenerate faces"
	puts "Removed $dloops degenerate loops"
	puts "Removed $dverts collinear vertices"
	puts "Removed $dverts2 spike vertices"
	puts "Removed $dverts3 coincident vertices"
}

for {set run 0} {$run < 5} {incr run} {
	puts "Cleaning pass $run"
	set coincident [expr $run > 1]
	set collinear 1
	set spikes [expr $run > 2]
	cleanareals $collinear $spikes $coincident
	world save -remove_unattributed [lindex $argv 1]
	puts "===================================="
}
# Save to output file.

tav_open world [lindex $argv 0]
