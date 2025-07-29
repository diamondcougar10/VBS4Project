tsa_open tsa [lindex $argv 0]

tsa modelapply m {
	m set -int VBS2_Model_NoCollision 1
	m set -int VBS2_Model_NoShadow 1
}
tsa save [lindex $argv 1]
